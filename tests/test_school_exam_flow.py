from datetime import date, timedelta

from app.handlers import router
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user


class FakeContentRepo:
    async def insert_words(self, level, words, learning_mode="GENERAL"):
        return len(words)

    async def get_word_ids(self, words, learning_mode="GENERAL"):
        return {}


class FakeSchoolAssignmentRepo:
    def __init__(self, wrong_questions=None):
        self.saved: list[tuple] = []
        self.wrong_questions = wrong_questions or []

    async def save(
        self,
        user_id,
        level,
        source_text,
        extracted_word_count,
        grammar_explanation,
        exam_question_count,
        exam_correct_count,
        exam_id=None,
        question_details=None,
    ):
        self.saved.append(
            (
                user_id,
                level,
                source_text,
                extracted_word_count,
                grammar_explanation,
                exam_question_count,
                exam_correct_count,
                exam_id,
                question_details,
            )
        )

    async def get_wrong_questions_for_exam(self, user_id, exam_id):
        return self.wrong_questions


class FakeSchoolExamsRepo:
    def __init__(self):
        self.created: list[tuple] = []
        self.reviews: list[tuple] = []
        self._exams: dict[int, dict] = {}
        self._next_id = 1

    def seed(self, subject, exam_date, unit_info="", teacher_notes=""):
        exam_id = self._next_id
        self._next_id += 1
        self._exams[exam_id] = {
            "id": exam_id,
            "subject": subject,
            "exam_date": exam_date,
            "unit_info": unit_info,
            "teacher_notes": teacher_notes,
        }
        return exam_id

    async def create(self, user_id, subject, exam_date, unit_info, teacher_notes):
        self.created.append((user_id, subject, exam_date, unit_info, teacher_notes))
        return self.seed(subject, exam_date, unit_info, teacher_notes)

    async def list_upcoming(self, user_id, today):
        return sorted([e for e in self._exams.values() if e["exam_date"] >= today], key=lambda e: e["exam_date"])

    async def list_all(self, user_id):
        return sorted(self._exams.values(), key=lambda e: e["exam_date"])

    async def get_by_id(self, exam_id, user_id):
        return self._exams.get(exam_id)

    async def record_review(self, exam_id, user_id, question_count, correct_count):
        self.reviews.append((exam_id, user_id, question_count, correct_count))


def _wire(monkeypatch, wrong_questions=None):
    fake_users = FakeUsersRepo()
    fake_content = FakeContentRepo()
    fake_school_assignment = FakeSchoolAssignmentRepo(wrong_questions=wrong_questions)
    fake_school_exams = FakeSchoolExamsRepo()
    fake_user_words = FakeUserWordsRepo()

    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "school_assignment_repo", fake_school_assignment)
    monkeypatch.setattr(router, "school_exams_repo", fake_school_exams)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text, reply_markup))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    async def fake_delete_message(chat_id, message_id):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    monkeypatch.setattr(router, "delete_message", fake_delete_message)
    return fake_users, fake_school_assignment, fake_school_exams, sent


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def test_exam_registration_full_flow(monkeypatch):
    fake_users, _, fake_school_exams, sent = _wire(monkeypatch)
    telegram_id = "1501"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1501}, "text": "/시험등록"}}))
    assert "과목명" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1501}, "text": "영어"}}))
    assert "날짜" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1501}, "text": "다음주"}}))
    assert "날짜 형식" in sent[-1][1]

    sent.clear()
    future_date = (date.today() + timedelta(days=10)).isoformat()
    run(router.handle_update({"message": {"chat": {"id": 1501}, "text": future_date}}))
    assert "단원" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1501}, "text": "3~5단원, 부정사"}}))
    assert "강조" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1501}, "text": "없음"}}))
    assert "등록되었습니다" in sent[-1][1]
    assert "D-10" in sent[-1][1]

    saved = fake_school_exams.created[0]
    assert saved[0] == 1  # user_id
    assert saved[1] == "영어"
    assert saved[3] == "3~5단원, 부정사"
    assert saved[4] == ""


def test_exam_list_shows_registered_exams(monkeypatch):
    fake_users, _, fake_school_exams, sent = _wire(monkeypatch)
    telegram_id = "1502"
    _setup_general_user(fake_users, telegram_id)
    fake_school_exams.seed("수학", date.today() + timedelta(days=3), "1~2단원", "공식 암기")

    run(router.handle_update({"message": {"chat": {"id": 1502}, "text": "/시험목록"}}))
    assert "수학" in sent[-1][1]
    assert "D-3" in sent[-1][1]
    assert "공식 암기" in sent[-1][1]


def test_exam_list_empty_guides_to_register(monkeypatch):
    fake_users, _, fake_school_exams, sent = _wire(monkeypatch)
    telegram_id = "1503"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1503}, "text": "/시험목록"}}))
    assert "등록된 시험이 없습니다" in sent[-1][1]


SAMPLE_TEXT = "The ubiquitous nature of smartphones has fundamentally altered how people communicate every day."

ANALYSIS = {
    "grammar_explanation": "현재완료 설명",
    "questions": [
        {"question": "Q1", "choices": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "E1"},
    ],
}


def test_school_assignment_auto_links_single_upcoming_exam(monkeypatch):
    fake_users, fake_school_assignment, fake_school_exams, sent = _wire(monkeypatch)
    telegram_id = "1504"
    _setup_general_user(fake_users, telegram_id)
    exam_id = fake_school_exams.seed("영어", date.today() + timedelta(days=5))

    async def fake_extract(text, level, max_words, learning_mode="GENERAL"):
        return []

    async def fake_analyze(text, level, question_count, learning_mode="GENERAL"):
        return ANALYSIS

    monkeypatch.setattr(router.custom_text_extractor, "extract_key_vocabulary", fake_extract)
    monkeypatch.setattr(router.school_assignment_analyzer, "analyze", fake_analyze)

    run(router.handle_update({"message": {"chat": {"id": 1504}, "text": "/수행평가"}}))
    assert "영어" in sent[-1][1]
    assert "연결합니다" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1504}, "text": SAMPLE_TEXT}}))

    # 예상문제 1문항 -> 정답 선택으로 세션 종료까지 진행
    kb_msg = next(m for m in sent if m[2] and "inline_keyboard" in m[2])
    cb_data = kb_msg[2]["inline_keyboard"][0][0]["callback_data"]
    run(router.handle_update(_callback_update(1504, cb_data)))

    saved = fake_school_assignment.saved[0]
    assert saved[7] == exam_id  # exam_id
    assert saved[8][0]["is_correct"] is True  # question_details


def test_school_assignment_asks_when_multiple_upcoming_exams(monkeypatch):
    fake_users, fake_school_assignment, fake_school_exams, sent = _wire(monkeypatch)
    telegram_id = "1505"
    _setup_general_user(fake_users, telegram_id)
    exam_a = fake_school_exams.seed("영어", date.today() + timedelta(days=5))
    fake_school_exams.seed("수학", date.today() + timedelta(days=8))

    run(router.handle_update({"message": {"chat": {"id": 1505}, "text": "/수행평가"}}))
    assert "어떤 시험" in sent[-1][1]
    keyboard = sent[-1][2]
    assert keyboard is not None

    sent.clear()
    run(router.handle_update(_callback_update(1505, f"schoolexamlink:{exam_a}")))
    assert "붙여넣어" in sent[-1][1]


def test_exam_review_without_registered_exam_guides_to_register(monkeypatch):
    fake_users, _, fake_school_exams, sent = _wire(monkeypatch)
    telegram_id = "1506"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1506}, "text": "/시험직전복습"}}))
    assert "등록된 예정 시험이 없습니다" in sent[-1][1]


def test_exam_review_with_no_wrong_questions(monkeypatch):
    fake_users, _, fake_school_exams, sent = _wire(monkeypatch, wrong_questions=[])
    telegram_id = "1507"
    _setup_general_user(fake_users, telegram_id)
    fake_school_exams.seed("영어", date.today() + timedelta(days=2))

    run(router.handle_update({"message": {"chat": {"id": 1507}, "text": "/시험직전복습"}}))
    assert "다시 볼 오답이 없어요" in sent[-1][1]


def test_exam_review_full_flow_with_wrong_questions(monkeypatch):
    wrong_questions = [
        {"question": "Q1", "choices": ["A", "B", "C", "D"], "correct_index": 2, "explanation": "E1", "is_correct": False},
        {"question": "Q2", "choices": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "E2", "is_correct": False},
    ]
    fake_users, _, fake_school_exams, sent = _wire(monkeypatch, wrong_questions=wrong_questions)
    telegram_id = "1508"
    _setup_general_user(fake_users, telegram_id)
    exam_id = fake_school_exams.seed("영어", date.today() + timedelta(days=2), "1~3단원", "듣기 평가 주의")

    run(router.handle_update({"message": {"chat": {"id": 1508}, "text": "/시험직전복습"}}))
    texts = [m[1] for m in sent]
    assert any("1~3단원" in t for t in texts)
    assert any("듣기 평가 주의" in t for t in texts)
    assert any("복습 1" in t for t in texts)

    sent.clear()
    run(router.handle_update(_callback_update(1508, "examreviewquiz:0:2")))  # 정답
    assert "정답입니다" in sent[0][1]
    assert "복습 2" in sent[1][1]

    sent.clear()
    run(router.handle_update(_callback_update(1508, "examreviewquiz:1:1")))  # 오답
    assert "오답입니다" in sent[-1][1]
    assert "시험직전복습 완료" in sent[-1][1]
    assert "1개 정답" in sent[-1][1]

    assert fake_school_exams.reviews[0] == (exam_id, 1, 2, 1)


def test_exam_review_picks_among_multiple_upcoming_exams(monkeypatch):
    wrong_questions = [
        {"question": "Q1", "choices": ["A", "B", "C", "D"], "correct_index": 0, "explanation": "E1", "is_correct": False},
    ]
    fake_users, _, fake_school_exams, sent = _wire(monkeypatch, wrong_questions=wrong_questions)
    telegram_id = "1509"
    _setup_general_user(fake_users, telegram_id)
    fake_school_exams.seed("영어", date.today() + timedelta(days=2))
    exam_b = fake_school_exams.seed("수학", date.today() + timedelta(days=4))

    run(router.handle_update({"message": {"chat": {"id": 1509}, "text": "/시험직전복습"}}))
    assert "어떤 시험" in sent[-1][1]

    sent.clear()
    run(router.handle_update(_callback_update(1509, f"examreviewpick:{exam_b}")))
    texts = [m[1] for m in sent]
    assert any("수학" in t for t in texts)
    assert any("복습 1" in t for t in texts)
