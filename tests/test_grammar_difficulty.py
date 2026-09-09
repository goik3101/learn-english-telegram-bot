from app.handlers import router
from tests.test_grammar_flow import _question_row
from tests.test_router import FakeUsersRepo, run


class FakeGrammarRepo:
    """test_grammar_flow.FakeGrammarRepo와 달리 record_answer를 실제로 누적해
    get_topic_recent_results/get_topic_accuracy_map이 그 기록을 반영하도록 만든 버전."""

    def __init__(self, questions_by_topic=None):
        self.questions_by_topic = questions_by_topic or {}
        self.answers: list[tuple] = []  # (user_id, question_id, is_correct, error_tag, is_review)
        self.topic_calls: list[str] = []
        self.review_calls: list[list[str]] = []

    def _question_by_id(self, question_id):
        for questions in self.questions_by_topic.values():
            for q in questions:
                if q["id"] == question_id:
                    return q
        return None

    async def has_completed_new_session_today(self, user_id):
        return False  # 테스트에서는 하루 제한을 신경 쓰지 않는다(관리자 우회와 동일한 효과)

    async def get_questions_for_topic(self, level, topic, limit, learning_mode="GENERAL"):
        self.topic_calls.append(topic)
        return self.questions_by_topic.get(topic, [])[:limit]

    async def get_random_questions(self, level, limit, learning_mode="GENERAL"):
        all_q = [q for qs in self.questions_by_topic.values() for q in qs]
        return all_q[:limit]

    async def get_topic_accuracy_map(self, user_id, min_attempts=3):
        by_topic: dict[str, list[bool]] = {}
        for uid, qid, is_correct, _error_tag, is_review in self.answers:
            if uid != user_id:
                continue
            q = self._question_by_id(qid)
            if q is None:
                continue
            by_topic.setdefault(q["topic"], []).append(is_correct)
        return {topic: sum(r) / len(r) for topic, r in by_topic.items() if len(r) >= min_attempts}

    async def get_topic_recent_results(self, user_id, topic, limit):
        results = [
            is_correct
            for uid, qid, is_correct, _error_tag, is_review in reversed(self.answers)
            if uid == user_id and not is_review and (self._question_by_id(qid) or {}).get("topic") == topic
        ]
        return results[:limit]

    async def get_weighted_review_questions(self, level, limit, learning_mode, weak_topics):
        self.review_calls.append(weak_topics)
        if weak_topics:
            weak_q = [q for topic in weak_topics for q in self.questions_by_topic.get(topic, [])]
            return weak_q[:limit]
        all_q = [q for qs in self.questions_by_topic.values() for q in qs]
        return all_q[:limit]

    async def record_answer(self, user_id, question_id, is_correct, error_tag, is_review):
        self.answers.append((user_id, question_id, is_correct, error_tag, is_review))


def _wire(monkeypatch, questions_by_topic=None):
    fake_users = FakeUsersRepo()
    fake_grammar = FakeGrammarRepo(questions_by_topic=questions_by_topic)
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


def _setup_general_user(fake_users, telegram_id):
    run(fake_users.create_pending_user(telegram_id))
    run(fake_users.approve_user(telegram_id))
    fake_users.users[telegram_id]["learning_mode"] = "GENERAL"
    fake_users.users[telegram_id]["placement_level"] = "beginner"


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def test_new_session_pulls_questions_for_current_curriculum_topic(monkeypatch):
    questions = {
        "현재시제": [_question_row(1, "현재시제", "She ___ to school.", ["go", "goes", "going", "went"], 1)],
    }
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions)
    telegram_id = "9101"
    _setup_general_user(fake_users, telegram_id)
    # grammar_topic_index=0 -> beginner 커리큘럼의 첫 주제는 "현재시제"

    run(router.handle_update({"message": {"chat": {"id": 9101}, "text": "/문법학습"}}))
    assert fake_grammar.topic_calls == ["현재시제"]
    assert "현재시제" in sent[-1][1] or "현재시제" in sent[0][1]


def test_advanced_placement_still_starts_at_first_curriculum_topic_not_its_own_level(monkeypatch):
    """버그리포트: "advanced"로 배치된 사용자가 현재완료도 모르는 상태에서 가정법을 먼저 만났음 —
    전역 순차 커리큘럼에서는 배치레벨과 무관하게 index=0("현재시제")부터 시작해야 한다."""
    questions = {
        "현재시제": [_question_row(1, "현재시제", "She ___ to school.", ["go", "goes", "going", "went"], 1)],
        "가정법": [_question_row(2, "가정법", "If I ___ rich...", ["am", "were", "was", "be"], 1)],
    }
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions)
    telegram_id = "9106"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["placement_level"] = "advanced"  # 배치는 advanced지만

    run(router.handle_update({"message": {"chat": {"id": 9106}, "text": "/문법학습"}}))

    assert fake_grammar.topic_calls == ["현재시제"]  # 가정법이 아니라 커리큘럼 첫 주제부터 나와야 함


def test_missing_content_for_current_topic_does_not_leak_other_topics(monkeypatch):
    """버그리포트: 현재 주제 콘텐츠가 없다고 레벨 전체 무작위로 대체하면 상위 주제가 새어나간다 —
    이제는 콘텐츠가 없으면 대체하지 않고 안내만 한다."""
    questions = {
        # "현재시제"(index 0) 콘텐츠가 아직 없고, 대신 다른 주제만 있는 상황을 흉내낸다.
        "가정법": [_question_row(2, "가정법", "If I ___ rich...", ["am", "were", "was", "be"], 1)],
    }
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions)
    telegram_id = "9107"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9107}, "text": "/문법학습"}}))

    assert fake_grammar.topic_calls == ["현재시제"]
    assert "가정법" not in sent[-1][1]
    assert "아직" in sent[-1][1] or "준비" in sent[-1][1]


def test_topic_advances_after_ten_correct_answers_across_sessions(monkeypatch):
    questions = {
        "현재시제": [
            _question_row(100 + i, "현재시제", f"Q{i} ___", ["a", "b", "c", "d"], 0) for i in range(5)
        ]
    }
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions)
    telegram_id = "9102"
    _setup_general_user(fake_users, telegram_id)

    # 5문항씩 두 세션(=10문항)을 전부 정답으로 통과한다.
    for session in range(2):
        run(router.handle_update({"message": {"chat": {"id": 9102}, "text": "/문법학습"}}))
        for i in range(5):
            question_id = 100 + i
            run(router.handle_update(_callback_update(9102, f"grammar:{question_id}:0")))

    assert fake_users.users[telegram_id]["grammar_topic_index"] == 1


def test_topic_does_not_advance_with_low_accuracy(monkeypatch):
    questions = {
        "현재시제": [
            _question_row(200 + i, "현재시제", f"Q{i} ___", ["a", "b", "c", "d"], 0) for i in range(5)
        ]
    }
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions)
    telegram_id = "9103"
    _setup_general_user(fake_users, telegram_id)

    # 10문항 중 절반 넘게 오답(정답 인덱스 0인데 항상 1로 답) -> 50% 미만 정답률
    for session in range(2):
        run(router.handle_update({"message": {"chat": {"id": 9103}, "text": "/문법학습"}}))
        for i in range(5):
            question_id = 200 + i
            run(router.handle_update(_callback_update(9103, f"grammar:{question_id}:1")))

    assert fake_users.users[telegram_id]["grammar_topic_index"] == 0


def test_review_weights_weak_topics(monkeypatch):
    questions = {
        "현재시제": [_question_row(1, "현재시제", "Q", ["a", "b", "c", "d"], 0) for _ in range(1)],
        "과거시제": [_question_row(2, "과거시제", "Q", ["a", "b", "c", "d"], 0) for _ in range(1)],
    }
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions)
    telegram_id = "9104"
    _setup_general_user(fake_users, telegram_id)

    # "과거시제"에서 오답 기록을 4개 쌓아 정답률을 낮춘다(가짜 question_id 재사용, 실제 문항 존재 불필요).
    fake_grammar.answers = [(1, 2, False, "과거시제", False)] * 4

    run(router.handle_update({"message": {"chat": {"id": 9104}, "text": "🔁 복습"}}))

    assert fake_grammar.review_calls == [["과거시제"]]


def test_review_falls_back_to_random_without_weak_topics(monkeypatch):
    questions = {"현재시제": [_question_row(1, "현재시제", "Q", ["a", "b", "c", "d"], 0)]}
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions)
    telegram_id = "9105"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9105}, "text": "🔁 복습"}}))

    assert fake_grammar.review_calls == [[]]
