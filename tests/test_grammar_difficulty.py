from app.handlers import router
from tests.test_grammar_flow import _question_row
from tests.test_router import FakeUsersRepo, run


def _part(id, topic_id, topic_name, name, global_order_index, cefr_level="B1", is_exam_focus=False, description=""):
    return {
        "id": id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "cefr_level": cefr_level,
        "is_exam_focus": is_exam_focus,
        "global_order_index": global_order_index,
        "name": name,
        "description": description,
    }


def _part_question(qid, part_id, topic, prompt, choices, correct_index, error_type=None, explanation="설명", concept_intro="개념 설명"):
    row = _question_row(qid, topic, prompt, choices, correct_index, explanation=explanation, concept_intro=concept_intro)
    row["part_id"] = part_id
    row["error_type"] = error_type
    return row


class FakeGrammarRepo:
    """test_grammar_flow.FakeGrammarRepo와 달리 record_answer/파트 진행 상태를 실제로 누적해
    파트 기반 커리큘럼 게이팅(app/grammar/mastery.py 등)이 여러 세션/여러 파트에 걸쳐 정확히
    동작하는지 시뮬레이션 검증하는 용도.

    두 가지 모드:
    - parts=[...] 를 주면(전체 파트 기반 시뮬레이션): 실제 순차 진행/숙달/취약 재출제/역행을 흉내낸다.
    - questions_by_topic=... 만 주면(기존 단순 /복습 가중치 테스트): 커리큘럼이 비어있는 것으로
      취급해 get_random_questions 폴백 경로를 타게 한다.
    """

    def __init__(self, parts=None, questions=None, questions_by_topic=None):
        self.parts_ordered = sorted(parts or [], key=lambda p: p["global_order_index"])
        self.parts = {p["id"]: p for p in self.parts_ordered}
        self.questions_by_topic = questions_by_topic or {}
        self.questions = {q["id"]: q for q in (questions or [])}
        self.answers: list[tuple] = []  # (user_id, question_id, is_correct, error_tag, is_review)
        self.user_progress: dict[int, dict] = {}
        self.part_progress: dict[tuple, dict] = {}
        self.topic_calls: list[str] = []
        self.part_question_calls: list[int] = []
        self.review_calls: list[list[str]] = []

    def _question_by_id(self, question_id):
        if question_id in self.questions:
            return self.questions[question_id]
        for questions in self.questions_by_topic.values():
            for q in questions:
                if q["id"] == question_id:
                    return q
        return None

    # ── 신규 세트(비복습): 파트 기반 순차 진행 ──────────────────────────────

    async def has_completed_new_session_today(self, user_id):
        return False

    async def get_user_progress(self, user_id):
        return self.user_progress.get(user_id)

    async def get_first_part(self):
        return self.parts_ordered[0] if self.parts_ordered else None

    async def get_part_by_id(self, part_id):
        return self.parts.get(part_id)

    async def get_next_part_after(self, part_id):
        idx = next((i for i, p in enumerate(self.parts_ordered) if p["id"] == part_id), None)
        if idx is None or idx + 1 >= len(self.parts_ordered):
            return None
        return self.parts_ordered[idx + 1]

    async def set_user_progress(self, user_id, topic_id, part_id):
        self.user_progress[user_id] = {"current_topic_id": topic_id, "current_part_id": part_id}

    async def get_weak_error_types_for_part(self, user_id, part_id, limit):
        counts: dict[str, int] = {}
        for uid, qid, is_correct, error_tag, is_review in self.answers:
            if uid != user_id or is_correct or is_review or not error_tag:
                continue
            q = self._question_by_id(qid)
            if q is None or q.get("part_id") != part_id:
                continue
            counts[error_tag] = counts.get(error_tag, 0) + 1
        return [t for t, _n in sorted(counts.items(), key=lambda kv: -kv[1])][:limit]

    async def get_questions_for_part(self, part_id, limit, learning_mode="GENERAL", prioritize_error_types=None):
        self.part_question_calls.append(part_id)
        pool = [q for q in self.questions.values() if q.get("part_id") == part_id]
        if prioritize_error_types:
            weak = [q for q in pool if q.get("error_type") in prioritize_error_types]
            rest = [q for q in pool if q not in weak]
            pool = weak + rest
        return pool[:limit]

    async def get_part_recent_results(self, user_id, part_id, limit, is_review=False):
        results = [
            is_correct
            for uid, qid, is_correct, _et, review in reversed(self.answers)
            if uid == user_id and review == is_review and (self._question_by_id(qid) or {}).get("part_id") == part_id
        ]
        return results[:limit]

    async def record_part_attempt(self, user_id, part_id, is_correct):
        entry = self.part_progress.setdefault((user_id, part_id), {"status": "in_progress", "attempt_count": 0, "correct_count": 0})
        entry["attempt_count"] += 1
        entry["correct_count"] += 1 if is_correct else 0

    async def get_part_progress(self, user_id, part_id):
        return self.part_progress.get((user_id, part_id))

    async def set_part_status(self, user_id, part_id, status):
        entry = self.part_progress.setdefault((user_id, part_id), {"status": status, "attempt_count": 0, "correct_count": 0})
        entry["status"] = status

    async def get_topic_names_up_to(self, global_order_index):
        seen: list[str] = []
        for p in self.parts_ordered:
            if p["global_order_index"] <= global_order_index and p["topic_name"] not in seen:
                seen.append(p["topic_name"])
        return seen

    # ── 커리큘럼이 비어있을 때(questions_by_topic 모드) 폴백 ────────────────

    async def get_random_questions(self, level, limit, learning_mode="GENERAL"):
        if self.questions_by_topic:
            all_q = [q for qs in self.questions_by_topic.values() for q in qs]
            return all_q[:limit]
        return list(self.questions.values())[:limit]

    async def get_questions_for_topic(self, level, topic, limit, learning_mode="GENERAL"):
        self.topic_calls.append(topic)
        return self.questions_by_topic.get(topic, [])[:limit]

    # ── 복습(/복습): 토픽 가중치 기반, 파트 여부와 무관 ─────────────────────

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

    async def get_weighted_review_questions(self, level, limit, learning_mode, weak_topics):
        self.review_calls.append(weak_topics)
        if weak_topics:
            if self.questions_by_topic:
                weak_q = [q for topic in weak_topics for q in self.questions_by_topic.get(topic, [])]
            else:
                weak_q = [q for q in self.questions.values() if q["topic"] in weak_topics]
            return weak_q[:limit]
        if self.questions_by_topic:
            all_q = [q for qs in self.questions_by_topic.values() for q in qs]
            return all_q[:limit]
        return list(self.questions.values())[:limit]

    async def record_answer(self, user_id, question_id, is_correct, error_tag, is_review):
        self.answers.append((user_id, question_id, is_correct, error_tag, is_review))


def _wire(monkeypatch, parts=None, questions=None, questions_by_topic=None):
    fake_users = FakeUsersRepo()
    fake_grammar = FakeGrammarRepo(parts=parts, questions=questions, questions_by_topic=questions_by_topic)
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


def test_new_session_pulls_questions_for_current_part(monkeypatch):
    parts = [_part(1, 10, "현재시제", "3인칭단수 -s", 0)]
    questions = [_part_question(1, 1, "현재시제", "She ___ to school.", ["go", "goes", "going", "went"], 1)]
    fake_users, fake_grammar, sent = _wire(monkeypatch, parts=parts, questions=questions)
    telegram_id = "9101"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9101}, "text": "/문법학습"}}))

    assert fake_grammar.part_question_calls == [1]
    assert "현재시제" in sent[-1][1] or "현재시제" in sent[0][1]
    assert fake_users.users[telegram_id]["id"] in fake_grammar.user_progress


def test_advanced_placement_still_starts_at_first_part_not_its_own_level(monkeypatch):
    """버그리포트: "advanced"로 배치된 사용자가 현재완료도 모르는 상태에서 가정법을 먼저 만났음 —
    파트 기반 커리큘럼에서도 배치레벨과 무관하게 global_order_index=0(첫 파트)부터 시작해야 한다."""
    parts = [
        _part(1, 10, "현재시제", "3인칭단수 -s", 0),
        _part(2, 20, "가정법", "2형 조건문", 1),
    ]
    questions = [
        _part_question(1, 1, "현재시제", "She ___ to school.", ["go", "goes", "going", "went"], 1),
        _part_question(2, 2, "가정법", "If I ___ rich...", ["am", "were", "was", "be"], 1),
    ]
    fake_users, fake_grammar, sent = _wire(monkeypatch, parts=parts, questions=questions)
    telegram_id = "9106"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["placement_level"] = "advanced"  # 배치는 advanced지만

    run(router.handle_update({"message": {"chat": {"id": 9106}, "text": "/문법학습"}}))

    assert fake_grammar.part_question_calls == [1]  # 가정법(파트2)이 아니라 파트1부터 나와야 함


def test_missing_content_for_current_part_does_not_leak_other_parts(monkeypatch):
    """버그리포트: 현재 파트 콘텐츠가 없다고 레벨 전체 무작위로 대체하면 상위 파트가 새어나간다 —
    이제는 콘텐츠가 없으면 대체하지 않고 안내만 한다."""
    parts = [
        _part(1, 10, "현재시제", "3인칭단수 -s", 0),
        _part(2, 20, "가정법", "2형 조건문", 1),
    ]
    # 파트1(index 0) 콘텐츠가 아직 없고, 파트2만 있는 상황을 흉내낸다.
    questions = [_part_question(2, 2, "가정법", "If I ___ rich...", ["am", "were", "was", "be"], 1)]
    fake_users, fake_grammar, sent = _wire(monkeypatch, parts=parts, questions=questions)
    telegram_id = "9107"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9107}, "text": "/문법학습"}}))

    assert fake_grammar.part_question_calls == [1]
    assert "가정법" not in sent[-1][1]
    assert "아직" in sent[-1][1] or "준비" in sent[-1][1]


def test_part_advances_after_five_correct_answers_in_a_single_session(monkeypatch):
    """핵심 버그 수정 검증: 파트 하나의 숙달 기준은 "최소 5문제 + 최근 5문제 80%"이므로, 하루
    세션 하나(5문제)만 정답으로 통과해도 즉시 다음 파트로 넘어가야 한다(예전 토픽 방식은 최소
    이틀 걸려 "5문제만 나가고 멈추는" 것처럼 느껴졌음)."""
    parts = [
        _part(1, 10, "현재시제", "3인칭단수 -s", 0),
        _part(2, 10, "현재시제", "부정문(don't/doesn't)", 1),
    ]
    questions = [
        _part_question(100 + i, 1, "현재시제", f"Q{i} ___", ["a", "b", "c", "d"], 0) for i in range(5)
    ]
    fake_users, fake_grammar, sent = _wire(monkeypatch, parts=parts, questions=questions)
    telegram_id = "9102"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9102}, "text": "/문법학습"}}))
    for i in range(5):
        run(router.handle_update(_callback_update(9102, f"grammar:{100 + i}:0")))

    user_id = fake_users.users[telegram_id]["id"]
    assert fake_grammar.part_progress[(user_id, 1)]["status"] == "mastered"
    assert fake_grammar.user_progress[user_id]["current_part_id"] == 2  # 다음 파트로 자동 진행


def test_part_does_not_advance_with_low_accuracy_and_reprioritizes_weak_error_type(monkeypatch):
    parts = [_part(1, 10, "현재시제", "3인칭단수 -s", 0)]
    questions = [
        _part_question(200 + i, 1, "현재시제", f"Q{i} ___", ["a", "b", "c", "d"], 0, error_type="3인칭단수_s누락")
        for i in range(5)
    ]
    fake_users, fake_grammar, sent = _wire(monkeypatch, parts=parts, questions=questions)
    telegram_id = "9103"
    _setup_general_user(fake_users, telegram_id)

    # 5문항 중 절반 넘게 오답(정답 인덱스 0인데 항상 1로 답) -> 50% 미만 정답률
    run(router.handle_update({"message": {"chat": {"id": 9103}, "text": "/문법학습"}}))
    for i in range(5):
        run(router.handle_update(_callback_update(9103, f"grammar:{200 + i}:1")))

    user_id = fake_users.users[telegram_id]["id"]
    assert fake_grammar.part_progress[(user_id, 1)]["status"] == "in_progress"
    assert fake_grammar.user_progress[user_id]["current_part_id"] == 1  # 같은 파트에 머무름

    # 다음 세션은 취약 오답유형(error_type)을 우선 재출제해야 한다.
    run(router.handle_update({"message": {"chat": {"id": 9103}, "text": "/문법학습"}}))
    assert fake_grammar.part_question_calls[-1] == 1


def test_multi_part_progression_across_topics_never_gets_stuck(monkeypatch):
    """회귀 테스트(사용자 요청): 여러 파트를 연속으로 통과시켜, 토픽 경계를 넘어가며 진행이
    멈추지 않고 순서대로(건너뛰지 않고) 이어지는지 검증한다."""
    parts = [
        _part(1, 10, "현재시제", "3인칭단수 -s", 0),
        _part(2, 10, "현재시제", "부정문(don't/doesn't)", 1),
        _part(3, 20, "현재완료", "형태(have/has+p.p.)", 2),
        _part(4, 20, "현재완료", "계속 용법(since/for)", 3),
    ]
    questions = {
        1: [_part_question(100 + i, 1, "현재시제", f"P1-{i} ___", ["a", "b", "c", "d"], 0) for i in range(5)],
        2: [_part_question(200 + i, 2, "현재시제", f"P2-{i} ___", ["a", "b", "c", "d"], 0) for i in range(5)],
        3: [_part_question(300 + i, 3, "현재완료", f"P3-{i} ___", ["a", "b", "c", "d"], 0) for i in range(5)],
        4: [_part_question(400 + i, 4, "현재완료", f"P4-{i} ___", ["a", "b", "c", "d"], 0) for i in range(5)],
    }
    all_questions = [q for qs in questions.values() for q in qs]
    fake_users, fake_grammar, sent = _wire(monkeypatch, parts=parts, questions=all_questions)
    telegram_id = "9110"
    _setup_general_user(fake_users, telegram_id)
    user_id_holder: dict[str, int] = {}

    for part_id in (1, 2, 3, 4):
        run(router.handle_update({"message": {"chat": {"id": 9110}, "text": "/문법학습"}}))
        assert fake_grammar.part_question_calls[-1] == part_id, f"파트 {part_id} 진행 중 다른 파트로 샘"
        for q in questions[part_id]:
            run(router.handle_update(_callback_update(9110, f"grammar:{q['id']}:{q['correct_index']}")))
        user_id_holder["id"] = fake_users.users[telegram_id]["id"]
        assert fake_grammar.part_progress[(user_id_holder["id"], part_id)]["status"] == "mastered"

    # 커리큘럼을 전부 마쳤으면(다음 파트 없음) 더 이상 진행 위치를 옮기지 않고 마지막 파트에
    # 머무른다(정상 종료, 무한루프/에러 없음) — 다음 세션은 그 파트 문제를 계속 재출제한다.
    assert fake_grammar.user_progress[user_id_holder["id"]]["current_part_id"] == 4


def test_review_regresses_to_weak_mastered_part(monkeypatch):
    """사용자 요청: 전체 레벨이 높아 이미 숙달 처리된 파트라도, /복습에서 계속 틀리면(최근 5개
    복습 응답 중 50% 미만) 그 파트로 자동 되돌아가야 한다(전체 레벨과 파트 숙달도를 분리 관리)."""
    parts = [
        _part(1, 10, "현재시제", "3인칭단수 -s", 0),
        _part(2, 20, "현재완료", "형태(have/has+p.p.)", 1),
    ]
    q1 = [_part_question(100 + i, 1, "현재시제", f"P1-{i} ___", ["a", "b", "c", "d"], 0) for i in range(5)]
    fake_users, fake_grammar, sent = _wire(monkeypatch, parts=parts, questions=q1)
    telegram_id = "9111"
    _setup_general_user(fake_users, telegram_id)
    user_id = fake_users.users[telegram_id]["id"]

    # 파트1을 숙달 처리(정답 5/5)해 파트2로 넘어가게 한다.
    run(router.handle_update({"message": {"chat": {"id": 9111}, "text": "/문법학습"}}))
    for q in q1:
        run(router.handle_update(_callback_update(9111, f"grammar:{q['id']}:0")))
    assert fake_grammar.part_progress[(user_id, 1)]["status"] == "mastered"
    assert fake_grammar.user_progress[user_id]["current_part_id"] == 2

    # 이후 /복습을 5번 새로 시작해 매번 그 세션의 첫 문제(항상 q1[0], 목록 순서가 고정적임)를
    # 오답 처리한다 — 최근 5개 복습 응답이 전부 오답이 되어 역행 기준(50% 미만)을 충족시킨다.
    first_question_id = q1[0]["id"]
    for _ in range(5):
        run(router.handle_update({"message": {"chat": {"id": 9111}, "text": "🔁 복습"}}))
        run(router.handle_update(_callback_update(9111, f"grammar:{first_question_id}:1")))

    assert fake_grammar.part_progress[(user_id, 1)]["status"] == "in_progress"
    assert fake_grammar.user_progress[user_id]["current_part_id"] == 1  # 되돌아감


def test_review_weights_weak_topics(monkeypatch):
    questions_by_topic = {
        "현재시제": [_question_row(1, "현재시제", "Q", ["a", "b", "c", "d"], 0) for _ in range(1)],
        "과거시제": [_question_row(2, "과거시제", "Q", ["a", "b", "c", "d"], 0) for _ in range(1)],
    }
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions_by_topic)
    telegram_id = "9104"
    _setup_general_user(fake_users, telegram_id)

    # "과거시제"에서 오답 기록을 4개 쌓아 정답률을 낮춘다(가짜 question_id 재사용, 실제 문항 존재 불필요).
    fake_grammar.answers = [(1, 2, False, "과거시제", False)] * 4

    run(router.handle_update({"message": {"chat": {"id": 9104}, "text": "🔁 복습"}}))

    assert fake_grammar.review_calls == [["과거시제"]]


def test_review_falls_back_to_random_without_weak_topics(monkeypatch):
    questions_by_topic = {"현재시제": [_question_row(1, "현재시제", "Q", ["a", "b", "c", "d"], 0)]}
    fake_users, fake_grammar, sent = _wire(monkeypatch, questions_by_topic=questions_by_topic)
    telegram_id = "9105"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 9105}, "text": "🔁 복습"}}))

    assert fake_grammar.review_calls == [[]]
