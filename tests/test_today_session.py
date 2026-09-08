from app.handlers import router
from tests.test_conversation_flow import FakeConversationRepo
from tests.test_grammar_flow import FakeGrammarRepo, _question_row
from tests.test_reading_flow import FakeReadingRepo, _passage_row
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user, _word_row


class FakeLearningSessionsRepo:
    def __init__(self):
        self.started: list[int] = []
        self.stages_completed: list[tuple[int, str]] = []
        self.completed: list[int] = []
        self.ai_call_count = 0

    async def start_today(self, user_id):
        self.started.append(user_id)

    async def mark_stage_complete(self, user_id, stage):
        self.stages_completed.append((user_id, stage))

    async def increment_ai_call_count(self, user_id, by=1):
        self.ai_call_count += by

    async def mark_completed(self, user_id):
        self.completed.append(user_id)


def _wire(
    monkeypatch,
    new_rows=None,
    grammar_questions=None,
    grammar_already_done=False,
    weak_topics=None,
    accuracy=None,
    reading_passage=None,
):
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(new_rows=new_rows)
    fake_grammar = FakeGrammarRepo(
        questions=grammar_questions,
        already_done_today=grammar_already_done,
        weak_topics=weak_topics,
        accuracy=accuracy,
    )
    fake_sessions = FakeLearningSessionsRepo()
    # 기본값은 지문 없음 -> 해석 단계는 자동으로 건너뛴다.
    fake_reading = FakeReadingRepo(passage_row=reading_passage)
    # 기본값은 "오늘 이미 완료" -> 회화 단계도 자동으로 건너뛰어 오늘의 학습이 종료된다(실제 AI 호출 방지).
    fake_conversation = FakeConversationRepo(already_done=True)

    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "grammar_repo", fake_grammar)
    monkeypatch.setattr(router, "learning_sessions_repo", fake_sessions)
    monkeypatch.setattr(router, "reading_repo", fake_reading)
    monkeypatch.setattr(router, "conversation_repo", fake_conversation)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    async def fake_delete_message(chat_id, message_id):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    monkeypatch.setattr(router, "delete_message", fake_delete_message)
    return fake_users, fake_user_words, fake_grammar, fake_sessions, fake_reading, fake_conversation, sent


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def test_today_session_shows_ai_focus_message_when_weak_topics_exist(monkeypatch):
    fake_users, fake_user_words, fake_grammar, fake_sessions, fake_reading, fake_conversation, sent = _wire(
        monkeypatch, new_rows=[], weak_topics=["가정법"], accuracy=0.4
    )
    telegram_id = "904"
    _setup_general_user(fake_users, telegram_id)

    async def fake_build_focus_message(level, weak_topics, accuracy, learning_mode="GENERAL"):
        assert weak_topics == ["가정법"]
        assert accuracy == 0.4
        return "최근 가정법에서 자주 틀리고 있어요!"

    monkeypatch.setattr(router.planner, "build_focus_message", fake_build_focus_message)

    run(router.handle_update({"message": {"chat": {"id": 904}, "text": "/오늘학습"}}))

    assert "최근 가정법에서 자주 틀리고 있어요" in sent[0][1]
    assert fake_sessions.ai_call_count == 1


def test_today_session_skips_ai_call_when_no_weak_topics(monkeypatch):
    fake_users, fake_user_words, fake_grammar, fake_sessions, fake_reading, fake_conversation, sent = _wire(monkeypatch, new_rows=[])
    telegram_id = "905"
    _setup_general_user(fake_users, telegram_id)

    async def fail_if_called(level, weak_topics, accuracy):
        raise AssertionError("AI 호출이 발생하면 안 됨 (취약 주제 없음)")

    monkeypatch.setattr(router.planner, "build_focus_message", fail_if_called)

    run(router.handle_update({"message": {"chat": {"id": 905}, "text": "/오늘학습"}}))
    assert fake_sessions.ai_call_count == 0


def test_today_session_chains_vocab_then_grammar_without_confirmation(monkeypatch):
    new_rows = [_word_row(70, "apple", "사과")]
    grammar_questions = [_question_row(90, "현재완료", "She ___ here.", ["live", "lived", "has lived", "living"], 2)]
    fake_users, fake_user_words, fake_grammar, fake_sessions, fake_reading, fake_conversation, sent = _wire(
        monkeypatch, new_rows=new_rows, grammar_questions=grammar_questions
    )
    telegram_id = "901"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 901}, "text": "/오늘학습"}}))
    assert fake_sessions.started == [1]
    assert "apple" in sent[-1][1]

    # 단어 카드에 [아는단어]로 응답 -> 큐가 1개뿐이라 바로 단어 단계 종료 -> 자동으로 문법 단계 시작
    sent.clear()
    run(router.handle_update(_callback_update(901, "vocab:known:70")))
    assert fake_sessions.stages_completed[0] == (1, "vocab")
    assert "현재완료" in sent[-1][1]  # 문법 문제(개념설명+문제)가 자동으로 옴

    # 문법 문제에 정답 -> 문항이 1개뿐이라 오늘의 학습 전체 완료
    sent.clear()
    run(router.handle_update(_callback_update(901, "grammar:90:2")))
    assert fake_sessions.stages_completed[1] == (1, "grammar")
    assert fake_sessions.completed == [1]
    assert "모두 마쳤습니다" in sent[-1][1]


def test_today_session_chains_through_reading_stage_when_passage_available(monkeypatch):
    grammar_questions = [_question_row(92, "가정법", "If I ___ rich.", ["am", "were", "was", "be"], 1)]
    fake_users, fake_user_words, fake_grammar, fake_sessions, fake_reading, fake_conversation, sent = _wire(
        monkeypatch,
        new_rows=[],
        grammar_questions=grammar_questions,
        reading_passage=_passage_row(),
    )
    telegram_id = "906"
    _setup_general_user(fake_users, telegram_id)

    async def fake_evaluate(passage_text, translation, learning_mode="GENERAL"):
        return True, "정확해요!"

    monkeypatch.setattr(router.reading_evaluator, "evaluate", fake_evaluate)

    run(router.handle_update({"message": {"chat": {"id": 906}, "text": "/오늘학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(906, "grammar:92:1")))

    # 문법 완료 후 확인질문 없이 바로 해석 지문이 옴
    assert "The cat sat" in sent[-1][1]
    assert fake_sessions.stages_completed[-1] == (1, "grammar")

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 906}, "text": "고양이가 매트에 앉았다."}}))

    assert fake_sessions.stages_completed[-1] == (1, "reading")
    assert fake_sessions.completed == [1]
    assert "모두 마쳤습니다" in sent[-1][1]


def test_today_session_skips_vocab_stage_when_nothing_to_learn(monkeypatch):
    grammar_questions = [_question_row(91, "관계대명사", "The book ___ I read.", ["who", "which", "whom", "whose"], 1)]
    fake_users, fake_user_words, fake_grammar, fake_sessions, fake_reading, fake_conversation, sent = _wire(
        monkeypatch, new_rows=[], grammar_questions=grammar_questions
    )
    telegram_id = "902"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 902}, "text": "/오늘학습"}}))

    # 단어 큐가 비어있으면 바로 문법 단계로 건너뛴다 (사용자에게 별도 확인 없이)
    assert "관계대명사" in sent[-1][1]
    assert ("vocab" in [s[1] for s in fake_sessions.stages_completed]) is False


def test_today_session_skips_grammar_when_already_done_today(monkeypatch):
    new_rows = [_word_row(71, "book", "책")]
    fake_users, fake_user_words, fake_grammar, fake_sessions, fake_reading, fake_conversation, sent = _wire(
        monkeypatch, new_rows=new_rows, grammar_already_done=True
    )
    telegram_id = "903"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 903}, "text": "/오늘학습"}}))
    sent.clear()
    run(router.handle_update(_callback_update(903, "vocab:known:71")))

    # 문법을 오늘 이미 했으면 건너뛰고 바로 오늘의 학습을 완료 처리한다
    assert fake_sessions.completed == [1]
    assert "모두 마쳤습니다" in sent[-1][1]
