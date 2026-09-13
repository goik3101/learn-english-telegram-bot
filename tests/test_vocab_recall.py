"""V2 학습 엔진: 신규 단어(첫 노출)와 복습(SRS due) 단어의 카드/recall UX 분리 검증.

실사용 피드백: "충분히 학습된 단어가 SRS 복습으로 다시 나올 때도 뜻을 곧바로 보여준 채
[아는단어]만 누르면 되던" 예전 구조가 진짜 회상(recall)을 검증하지 않는다는 문제 — 복습
카드는 뜻/예문/연상법을 가리고 [기억남]/[모르겠음]을 먼저 받은 뒤에만 공개해야 한다.
"""

from app.handlers import router
from app.vocab import service as vocab_service
from tests.test_vocab_flow import (
    FakeContentGenerator,
    FakeContentRepo,
    FakeLearningSessionsRepo,
    FakeUserWordsRepo,
    _callback_update,
    _due_row,
    _setup_general_user,
    _word_row,
)
from tests.test_router import FakeUsersRepo, NullGrammarRepo, run


def _wire(monkeypatch, due_rows=None, new_rows=None):
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(due_rows=due_rows, new_rows=new_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "learning_sessions_repo", FakeLearningSessionsRepo())
    monkeypatch.setattr(router, "content_repo", FakeContentRepo(topic_word_rows=new_rows))
    monkeypatch.setattr(router, "content_generator", FakeContentGenerator())
    monkeypatch.setattr(router, "grammar_repo", NullGrammarRepo())
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text, reply_markup))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    return fake_users, fake_user_words, sent


def test_new_word_card_keeps_full_reveal_ux(monkeypatch):
    """신규 단어 최초 노출은 기존 방식(전체공개) 그대로 유지되어야 한다."""
    new_rows = [_word_row(1, "apple", "사과")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "801"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 801}, "text": "/단어학습"}}))

    card_text = sent[-1][1]
    assert "🆕 신규" in card_text
    assert "뜻: 사과" in card_text  # 뜻이 최초 카드에 그대로 공개됨(기존 방식 유지)
    keyboard = sent[-1][2]
    callback_datas = [btn["callback_data"] for row in keyboard["inline_keyboard"] for btn in row]
    assert "vocab:known:1" in callback_datas
    assert "vocab:unknown:1" in callback_datas


def test_review_word_card_hides_meaning_until_recall_choice(monkeypatch):
    """복습(SRS due) 단어는 뜻/예문/연상법을 처음부터 공개하지 않는다 — 단어+발음+회상 질문만."""
    due_rows = [_due_row(70, "run", "달리다")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, due_rows=due_rows)
    telegram_id = "802"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 802}, "text": "/단어학습"}}))

    card_text = sent[-1][1]
    assert "🔁 복습" in card_text
    assert "run" in card_text
    assert "달리다" not in card_text  # 뜻이 아직 공개되면 안 됨
    assert "예문" not in card_text
    keyboard = sent[-1][2]
    callback_datas = [btn["callback_data"] for row in keyboard["inline_keyboard"] for btn in row]
    assert "vocab:recallknown:70" in callback_datas
    assert "vocab:recallunknown:70" in callback_datas
    # 예전처럼 그냥 눌러서 끝나는 known/unknown 버튼은 없어야 한다.
    assert "vocab:known:70" not in callback_datas
    assert "vocab:unknown:70" not in callback_datas


def test_recall_known_reveals_meaning_and_counts_as_correct(monkeypatch):
    due_rows = [_due_row(70, "run", "달리다")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, due_rows=due_rows)
    telegram_id = "803"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 803}, "text": "/단어학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(803, "vocab:recallknown:70")))

    reveal_text = sent[0][1]
    assert "달리다" in reveal_text  # 선택 이후에는 뜻이 공개됨

    call = fake_user_words.progress_calls[0]
    word_id, status, _, _, _, mastery, _, is_correct = call[1:]
    assert word_id == 70
    assert status == "known"
    assert is_correct is True  # 기억남 -> correct 처리


def test_recall_unknown_reveals_meaning_and_counts_as_wrong(monkeypatch):
    due_rows = [_due_row(71, "eat", "먹다")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, due_rows=due_rows)
    telegram_id = "804"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 804}, "text": "/단어학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(804, "vocab:recallunknown:71")))

    reveal_text = sent[0][1]
    assert "먹다" in reveal_text  # 모르겠다고 해도 뜻은 공개된다

    call = fake_user_words.progress_calls[0]
    word_id, status, _, _, _, mastery, consecutive_correct, is_correct = call[1:]
    assert word_id == 71
    assert status == "learning"
    assert is_correct is False  # 모르겠음 -> wrong 처리
    assert mastery == "learning_step_1"  # 오답이므로 학습단계 처음으로 리셋
    assert consecutive_correct == 0


def test_recall_flow_advances_to_next_word_normally(monkeypatch):
    """뜻 공개 이후 기존 흐름(다음 카드로 진행)이 정상 작동해야 한다."""
    due_rows = [_due_row(70, "run", "달리다"), _due_row(71, "eat", "먹다")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, due_rows=due_rows)
    telegram_id = "805"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 805}, "text": "/단어학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(805, "vocab:recallknown:70")))

    # 다음 카드(eat)도 recall 프롬프트로 정상 전송돼야 한다.
    next_card_text = sent[-1][1]
    assert "eat" in next_card_text
    assert "먹다" not in next_card_text  # 다음 카드도 아직 안 열림


def test_recall_callback_with_expired_session_notifies_user(monkeypatch):
    fake_users, fake_user_words, sent = _wire(monkeypatch)
    telegram_id = "806"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update(_callback_update(806, "vocab:recallknown:999")))

    assert sent, "세션이 없을 때도 사용자에게 응답이 가야 한다"
    assert "만료" in sent[-1][1] or "다시 시작" in sent[-1][1]


def test_recall_callback_with_mismatched_word_id_notifies_user(monkeypatch):
    due_rows = [_due_row(70, "run", "달리다")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, due_rows=due_rows)
    telegram_id = "807"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 807}, "text": "/단어학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(807, "vocab:recallknown:9999")))  # 지연된/엉뚱한 콜백

    assert sent, "word_id가 안 맞아도 사용자에게 응답이 가야 한다"
    assert "만료" in sent[-1][1] or "다시 시작" in sent[-1][1]


def test_duplicate_recall_click_is_ignored_without_double_processing(monkeypatch):
    """세션/콜백 만료 후 처리: 이미 처리된 recall 카드에 같은 콜백이 중복으로 와도 SRS 기록이
    두 번 쌓이면 안 된다."""
    due_rows = [_due_row(70, "run", "달리다")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, due_rows=due_rows)
    telegram_id = "808"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 808}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(808, "vocab:recallknown:70")))
    calls_after_first = len(fake_user_words.progress_calls)
    # 같은 단어에 대해 지연된 중복 클릭(이미 다음 카드로 넘어간 상태)
    run(router.handle_update(_callback_update(808, "vocab:recallknown:70")))

    assert len(fake_user_words.progress_calls) == calls_after_first  # 추가 기록 없음
