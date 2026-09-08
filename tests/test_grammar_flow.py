from app.handlers import router
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import _setup_general_user


class FakeGrammarRepo:
    def __init__(self, questions=None, already_done_today=False, weak_topics=None, accuracy=None):
        self.questions = questions or []
        self.already_done_today = already_done_today
        self.weak_topics = weak_topics or []
        self.accuracy = accuracy
        self.recorded: list[tuple] = []
        self.mode_calls: list[str] = []

    async def get_random_questions(self, level, limit, learning_mode="GENERAL"):
        self.mode_calls.append(learning_mode)
        return self.questions[:limit]

    async def get_questions_for_topic(self, level, topic, limit, learning_mode="GENERAL"):
        self.mode_calls.append(learning_mode)
        return self.questions[:limit]

    async def get_topic_accuracy_map(self, user_id, min_attempts=3):
        return {}

    async def get_topic_recent_results(self, user_id, topic, limit):
        return []

    async def get_weighted_review_questions(self, level, limit, learning_mode, weak_topics):
        return self.questions[:limit]

    async def has_completed_new_session_today(self, user_id):
        return self.already_done_today

    async def get_weak_topics(self, user_id, limit):
        return self.weak_topics[:limit]

    async def get_overall_accuracy(self, user_id):
        return self.accuracy

    async def record_answer(self, user_id, question_id, is_correct, error_tag, is_review):
        self.recorded.append((user_id, question_id, is_correct, error_tag, is_review))


def _question_row(qid, topic, prompt, choices, correct_index, explanation="설명", concept_intro="개념 설명"):
    return {
        "id": qid,
        "topic": topic,
        "concept_intro": concept_intro,
        "prompt": prompt,
        "choices": choices,
        "correct_index": correct_index,
        "explanation": explanation,
    }


def _wire(monkeypatch, questions=None, already_done_today=False):
    fake_users = FakeUsersRepo()
    fake_grammar = FakeGrammarRepo(questions=questions, already_done_today=already_done_today)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "grammar_repo", fake_grammar)
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
    return fake_users, fake_grammar, sent


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def test_grammar_session_correct_and_incorrect_answers_recorded(monkeypatch):
    questions = [
        _question_row(1, "현재완료", "She ___ here for years.", ["live", "has lived", "living", "lived"], 1),
        _question_row(2, "관계대명사", "The book ___ I read was great.", ["who", "which", "whom", "whose"], 1),
    ]
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions=questions)
    telegram_id = "801"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 801}, "text": "/문법학습"}}))
    assert "현재완료" in sent[-1][1]

    sent.clear()
    run(router.handle_update(_callback_update(801, "grammar:1:1")))  # 정답
    assert "정답입니다" in sent[0][1]
    assert "관계대명사" in sent[-1][1]

    sent.clear()
    run(router.handle_update(_callback_update(801, "grammar:2:0")))  # 오답 (who)
    assert "오답입니다" in sent[0][1]
    assert "완료" in sent[-1][1]
    assert "1개 정답" in sent[-1][1]

    assert fake_grammar.recorded[0] == (1, 1, True, None, False)
    assert fake_grammar.recorded[1] == (1, 2, False, "관계대명사", False)


def test_concept_intro_sent_before_the_question(monkeypatch):
    questions = [
        _question_row(
            9,
            "도치구문",
            "Never ___ such a beautiful sunset.",
            ["I have seen", "have I seen", "I saw", "did I saw"],
            1,
            concept_intro="부정어가 문두에 오면 주어와 동사가 도치된다.",
        )
    ]
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions=questions)
    telegram_id = "805"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 805}, "text": "/문법학습"}}))

    # sent[0]=세션 시작 안내, sent[1]=개념 설명, sent[2]=문제(버튼 포함)
    assert "도치되면" in sent[1][1] or "도치" in sent[1][1]
    assert "Never" in sent[2][1]


def test_new_session_blocked_if_already_done_today(monkeypatch):
    fake_users, fake_grammar, sent = _wire(monkeypatch, already_done_today=True)
    telegram_id = "802"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 802}, "text": "/문법학습"}}))
    assert "이미 완료" in sent[-1][1]


def test_admin_bypasses_daily_limit(monkeypatch):
    questions = [_question_row(6, "관계부사", "This is the place ___ I was born.", ["who", "which", "where", "when"], 2)]
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions=questions, already_done_today=True)
    telegram_id = "804"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["role"] = "admin"

    run(router.handle_update({"message": {"chat": {"id": 804}, "text": "/문법학습"}}))
    assert "관계부사" in sent[-1][1]  # 하루 1회 제한과 무관하게 새 세트가 바로 시작됨


def test_review_command_allowed_even_if_new_session_done_today(monkeypatch):
    questions = [_question_row(5, "가정법", "If I ___ rich, I would travel.", ["am", "were", "was", "be"], 1)]
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions=questions, already_done_today=True)
    telegram_id = "803"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 803}, "text": "/복습"}}))
    assert "가정법" in sent[-1][1]

    sent.clear()
    run(router.handle_update(_callback_update(803, "grammar:5:1")))
    assert "복습 완료" in sent[-1][1]
    assert fake_grammar.recorded[-1] == (1, 5, True, None, True)
