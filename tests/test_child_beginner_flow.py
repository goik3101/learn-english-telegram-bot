import json

from app.child_beginner import curriculum, service
from app.child_beginner.generator import generate_content
from app.handlers import router
from tests.test_router import FakeUsersRepo, run


def test_build_alphabet_quiz_answer_is_always_in_choices():
    quiz = curriculum.build_alphabet_quiz(5)
    assert len(quiz) == 5
    for q in quiz:
        assert len(q.choices) == 4
        assert 0 <= q.correct_index < 4
        assert len(set(q.choices)) == 4  # 중복 선택지 없음


def test_build_phonics_quiz_answer_is_always_in_choices():
    quiz = curriculum.build_phonics_quiz(5)
    assert len(quiz) == 5
    for q in quiz:
        assert len(q.choices) == 4
        assert 0 <= q.correct_index < 4


def test_card_stage_progresses_through_all_cards_then_quiz():
    telegram_id = "child-svc-1"
    cards = curriculum.ALPHABET[:3]
    quiz = [service.StageQuizItem(index=0, passage_text=None, prompt="Q", choices=["a", "b", "c", "d"], correct_index=0)]
    service.start_card_stage(telegram_id, 0, cards, quiz)

    assert service.current_card(telegram_id) == cards[0]
    assert service.advance_card(telegram_id) == cards[1]
    assert service.advance_card(telegram_id) == cards[2]
    assert service.advance_card(telegram_id) is None  # 카드 끝 -> 퀴즈 단계로 전환

    session = service.get_session(telegram_id)
    assert session.phase == "quiz"
    assert service.current_quiz_item(telegram_id) == quiz[0]
    service.finish(telegram_id)


def test_quiz_stage_submit_answer_correct_and_incorrect():
    telegram_id = "child-svc-2"
    quiz = [
        service.StageQuizItem(index=0, passage_text=None, prompt="Q1", choices=["a", "b", "c", "d"], correct_index=1),
        service.StageQuizItem(index=1, passage_text=None, prompt="Q2", choices=["a", "b", "c", "d"], correct_index=2),
    ]
    service.start_quiz_stage(telegram_id, 3, quiz)

    result = service.submit_quiz_answer(telegram_id, 0, 1)
    assert result.is_correct is True
    assert result.finished is False
    assert result.next_item == quiz[1]

    result2 = service.submit_quiz_answer(telegram_id, 1, 0)
    assert result2.is_correct is False
    assert result2.finished is True
    assert result2.correct == 1
    assert result2.total == 2


def test_quiz_stage_rejects_stale_answer():
    telegram_id = "child-svc-3"
    quiz = [service.StageQuizItem(index=0, passage_text=None, prompt="Q1", choices=["a", "b", "c", "d"], correct_index=0)]
    service.start_quiz_stage(telegram_id, 2, quiz)
    service.submit_quiz_answer(telegram_id, 0, 0)  # 완료 -> 세션 삭제됨

    assert service.submit_quiz_answer(telegram_id, 0, 0) is None


def test_generator_filters_malformed_items(monkeypatch):
    import app.child_beginner.generator as generator_module

    payload = [
        {"prompt": "cat", "meaning_ko": "고양이", "choices": ["고양이", "개", "새", "쥐"], "correct_index": 0},
        {"prompt": "bad", "meaning_ko": "누락"},  # choices 없음 -> 필터링
    ]

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps(payload)

    monkeypatch.setattr(generator_module, "generate_json", fake_generate_json)

    result = run(generate_content(2, 2))
    assert len(result) == 1
    assert result[0]["prompt"] == "cat"


def test_generator_requires_passage_text_for_stage5(monkeypatch):
    import app.child_beginner.generator as generator_module

    payload = [
        {"prompt": "질문?", "meaning_ko": "설명", "choices": ["1", "2", "3", "4"], "correct_index": 0},  # passage_text 없음
    ]

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps(payload)

    monkeypatch.setattr(generator_module, "generate_json", fake_generate_json)

    result = run(generate_content(5, 1))
    assert result == []


# --- 라우터 통합 테스트 ---


class FakeChildBeginnerRepo:
    def __init__(self, content_rows=None):
        self.content_rows = content_rows or []
        self.completed_stages: list[tuple] = []

    async def get_content_for_stage(self, stage, limit):
        return self.content_rows[:limit]

    async def mark_stage_completed(self, user_id, stage):
        self.completed_stages.append((user_id, stage))


def _wire(monkeypatch, content_rows=None):
    fake_users = FakeUsersRepo()
    fake_child_repo = FakeChildBeginnerRepo(content_rows=content_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "child_beginner_repo", fake_child_repo)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []
    voices: list[bytes] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text, reply_markup))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    async def fake_delete_message(chat_id, message_id):
        pass

    async def fake_send_voice(chat_id, audio_bytes, caption=None):
        voices.append(audio_bytes)

    async def fake_get_speech_audio(text, **kwargs):
        return b"fake-audio:" + text.encode("utf-8")

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    monkeypatch.setattr(router, "delete_message", fake_delete_message)
    monkeypatch.setattr(router, "send_voice", fake_send_voice)
    monkeypatch.setattr(router.tts, "get_speech_audio", fake_get_speech_audio)
    return fake_users, fake_child_repo, sent, voices


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def _all_buttons(reply_markup):
    return [b for row in reply_markup["inline_keyboard"] for b in row]


def test_age_8_starts_stage0_alphabet_cards(monkeypatch):
    fake_users, _, sent, _ = _wire(monkeypatch)
    telegram_id = "3001"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))

    run(router.handle_update({"message": {"chat": {"id": 3001}, "text": "/start"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 3001}, "text": "8"}}))

    assert fake_users.users[telegram_id]["learning_mode"] == "CHILD_BEGINNER"
    texts = "\n".join(m[1] for m in sent)
    assert "알파벳" in texts
    assert "Apple" in texts


def test_full_stage0_flow_advances_to_stage1(monkeypatch):
    fake_users, fake_child_repo, sent, _ = _wire(monkeypatch)
    telegram_id = "3002"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    run(router.handle_update({"message": {"chat": {"id": 3002}, "text": "/start"}}))
    run(router.handle_update({"message": {"chat": {"id": 3002}, "text": "8"}}))

    # 26개 카드를 전부 "다음"으로 넘긴다
    for _ in range(26):
        sent.clear()
        run(router.handle_update(_callback_update(3002, "childcard:next")))

    assert any("퀴즈" in m[1] for m in sent)

    # 퀴즈 5문항을 전부 첫 번째 선택지로 답한다 (정답 여부와 무관하게 진행되는지만 확인)
    for _ in range(5):
        kb = sent[-1][2]
        buttons = _all_buttons(kb)
        cb_data = buttons[0]["callback_data"]
        sent.clear()
        run(router.handle_update(_callback_update(3002, cb_data)))

    assert "단계를 모두 마쳤어요" in sent[-1][1]
    assert fake_users.users[telegram_id]["child_stage"] == 1
    assert fake_child_repo.completed_stages == [(1, 0)]


def test_stage2_uses_content_bank_quiz_only(monkeypatch):
    content_rows = [
        {"passage_text": None, "prompt": "cat", "meaning_ko": "고양이", "choices": ["고양이", "개", "새", "쥐"], "correct_index": 0}
        for _ in range(5)
    ]
    fake_users, fake_child_repo, sent, _ = _wire(monkeypatch, content_rows=content_rows)
    telegram_id = "3003"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "CHILD_BEGINNER"
    fake_users.users[telegram_id]["child_stage"] = 2

    run(router.handle_update({"message": {"chat": {"id": 3003}, "text": "🎈 오늘 공부하기"}}))
    assert "cat" in sent[-1][1]  # 카드 단계 없이 바로 MCQ

    for _ in range(5):
        kb = sent[-1][2]
        buttons = _all_buttons(kb)
        sent.clear()
        run(router.handle_update(_callback_update(3003, buttons[0]["callback_data"])))

    assert "기초 단어" in sent[-1][1]
    assert fake_users.users[telegram_id]["child_stage"] == 3


def test_stage_with_no_content_shows_friendly_message(monkeypatch):
    fake_users, _, sent, _ = _wire(monkeypatch, content_rows=[])
    telegram_id = "3004"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "CHILD_BEGINNER"
    fake_users.users[telegram_id]["child_stage"] = 4

    run(router.handle_update({"message": {"chat": {"id": 3004}, "text": "🎈 오늘 공부하기"}}))
    assert "준비되지 않았어요" in sent[-1][1]


def test_progress_shows_completed_and_current_stage(monkeypatch):
    fake_users, _, sent, _ = _wire(monkeypatch)
    telegram_id = "3005"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "CHILD_BEGINNER"
    fake_users.users[telegram_id]["child_stage"] = 2

    run(router.handle_update({"message": {"chat": {"id": 3005}, "text": "⭐ 내 진도"}}))
    text = sent[-1][1]
    assert "✅ 알파벳" in text
    assert "✅ 파닉스" in text
    assert "👉 기초 단어" in text
    assert "⬜ 기초 문장" in text


def test_unrecognized_input_shows_child_menu_not_general_menu(monkeypatch):
    fake_users, _, sent, _ = _wire(monkeypatch)
    telegram_id = "3006"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "CHILD_BEGINNER"

    run(router.handle_update({"message": {"chat": {"id": 3006}, "text": "asdkfj"}}))
    assert "골라주세요" in sent[-1][1]
    assert "이해하지 못했어요" not in sent[-1][1]


# --- Stage6(듣기말하기) ---

STAGE6_CONTENT_ROWS = [
    {"passage_text": None, "prompt": "cat", "meaning_ko": "고양이", "choices": ["고양이", "개", "새", "쥐"], "correct_index": 0}
    for _ in range(5)
]


def test_stage6_sends_voice_before_choices(monkeypatch):
    fake_users, _, sent, voices = _wire(monkeypatch, content_rows=STAGE6_CONTENT_ROWS)
    telegram_id = "3007"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "CHILD_BEGINNER"
    fake_users.users[telegram_id]["child_stage"] = 6

    run(router.handle_update({"message": {"chat": {"id": 3007}, "text": "🎈 오늘 공부하기"}}))

    assert voices == [b"fake-audio:cat"]
    # 듣기 문제이므로 단어 텍스트("cat")가 질문 메시지에 그대로 노출되면 안 된다.
    assert "cat" not in sent[-1][1]
    assert "무슨 뜻일까요" in sent[-1][1]


def test_stage6_completes_listening_then_waits_for_voice_practice(monkeypatch):
    fake_users, fake_child_repo, sent, voices = _wire(monkeypatch, content_rows=STAGE6_CONTENT_ROWS)
    telegram_id = "3008"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "CHILD_BEGINNER"
    fake_users.users[telegram_id]["child_stage"] = 6

    run(router.handle_update({"message": {"chat": {"id": 3008}, "text": "🎈 오늘 공부하기"}}))

    for _ in range(5):
        kb = sent[-1][2]
        buttons = _all_buttons(kb)
        sent.clear()
        run(router.handle_update(_callback_update(3008, buttons[0]["callback_data"])))

    assert any("듣기 연습 완료" in m[1] for m in sent)
    assert any("녹음해서 보내주세요" in m[1] for m in sent)
    # 아직 말하기 연습이 안 끝났으니 진도/child_stage는 그대로 6이어야 한다.
    assert fake_users.users[telegram_id]["child_stage"] == 6
    assert fake_child_repo.completed_stages == []

    # 텍스트로 답하면 음성으로 보내달라고 다시 안내
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 3008}, "text": "다 했어요"}}))
    assert "목소리로 녹음해서 보내주세요" in sent[-1][1]
    assert fake_users.users[telegram_id]["child_stage"] == 6

    # 음성메시지를 보내면 그제서야 완료 처리된다
    sent.clear()
    run(
        router.handle_update(
            {"message": {"chat": {"id": 3008}, "voice": {"file_id": "abc", "duration": 3}}}
        )
    )
    assert "단계를 모두 마쳤어요" in sent[-1][1]
    assert fake_users.users[telegram_id]["child_stage"] == 7
    assert fake_child_repo.completed_stages == [(1, 6)]


def test_progress_screen_includes_listening_speaking_stage(monkeypatch):
    fake_users, _, sent, _ = _wire(monkeypatch)
    telegram_id = "3009"
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "CHILD_BEGINNER"
    fake_users.users[telegram_id]["child_stage"] = 6

    run(router.handle_update({"message": {"chat": {"id": 3009}, "text": "⭐ 내 진도"}}))
    text = sent[-1][1]
    assert "👉 듣기 말하기" in text
