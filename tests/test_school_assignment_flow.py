from app.handlers import router
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user


class FakeContentRepo:
    def __init__(self):
        self.inserted_words: list[tuple] = []
        self._next_id = 700

    async def insert_words(self, level, words):
        self.inserted_words.append((level, words))
        return len(words)

    async def get_word_ids(self, words):
        ids = {}
        for w in words:
            ids[w] = self._next_id
            self._next_id += 1
        return ids


class FakeSchoolAssignmentRepo:
    def __init__(self):
        self.saved: list[tuple] = []

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


class FakeSchoolExamsRepo:
    def __init__(self, upcoming=None):
        self.upcoming = upcoming or []

    async def list_upcoming(self, user_id, today):
        return self.upcoming


def _wire(monkeypatch):
    fake_users = FakeUsersRepo()
    fake_content = FakeContentRepo()
    fake_school_assignment = FakeSchoolAssignmentRepo()
    fake_school_exams = FakeSchoolExamsRepo()
    fake_user_words = FakeUserWordsRepo()

    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "school_assignment_repo", fake_school_assignment)
    monkeypatch.setattr(router, "school_exams_repo", fake_school_exams)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None):
        sent.append((chat_id, text))

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    async def fake_delete_message(chat_id, message_id):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    monkeypatch.setattr(router, "delete_message", fake_delete_message)
    return fake_users, fake_content, fake_school_assignment, fake_user_words, sent


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


SAMPLE_TEXT = "The ubiquitous nature of smartphones has fundamentally altered how people communicate every day."

ANALYSIS = {
    "grammar_explanation": "현재완료(has altered)는 과거에 시작되어 현재까지 영향을 미치는 변화를 나타냅니다.",
    "questions": [
        {
            "question": "What does 'ubiquitous' mean in the passage?",
            "choices": ["어디에나 있는", "희귀한", "위험한", "느린"],
            "correct_index": 0,
            "explanation": "본문에서 스마트폰이 어디에나 있다는 의미로 쓰였습니다.",
        },
        {
            "question": "Which tense is used in 'has fundamentally altered'?",
            "choices": ["단순과거", "현재완료", "미래", "현재진행"],
            "correct_index": 1,
            "explanation": "has + p.p. 형태는 현재완료입니다.",
        },
    ],
}


def test_school_assignment_full_flow_with_extracted_word_and_exam(monkeypatch):
    fake_users, fake_content, fake_school_assignment, fake_user_words, sent = _wire(monkeypatch)
    telegram_id = "1401"
    _setup_general_user(fake_users, telegram_id)

    async def fake_extract(text, level, max_words):
        assert text == SAMPLE_TEXT
        return [
            {
                "word": "ubiquitous",
                "meaning_ko": "어디에나 있는",
                "part_of_speech": "adjective",
                "pronunciation": "/juːˈbɪkwɪtəs/",
                "example_sentence": SAMPLE_TEXT,
                "example_translation": "스마트폰의 편재성...",
            }
        ]

    async def fake_analyze(text, level, question_count):
        assert text == SAMPLE_TEXT
        return ANALYSIS

    monkeypatch.setattr(router.custom_text_extractor, "extract_key_vocabulary", fake_extract)
    monkeypatch.setattr(router.school_assignment_analyzer, "analyze", fake_analyze)

    run(router.handle_update({"message": {"chat": {"id": 1401}, "text": "/수행평가"}}))
    assert "붙여넣어" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1401}, "text": SAMPLE_TEXT}}))
    assert "ubiquitous" in sent[-1][1]
    assert fake_content.inserted_words[0][0] == "beginner"

    sent.clear()
    run(router.handle_update(_callback_update(1401, "vocab:known:700")))
    # 단어 카드 완료 -> 문법해설 메시지 -> 첫 예상문제 순으로 전송된다
    texts = [t for _, t in sent]
    assert any("현재완료" in t for t in texts)
    assert any("예상문제 1" in t for t in texts)

    sent.clear()
    run(router.handle_update(_callback_update(1401, "examquiz:0:0")))
    assert "정답입니다" in sent[0][1]
    assert "예상문제 2" in sent[1][1]

    sent.clear()
    run(router.handle_update(_callback_update(1401, "examquiz:1:0")))
    assert "오답입니다" in sent[-1][1]
    assert "학교 수행평가 학습 완료" in sent[-1][1]
    assert "1개 정답" in sent[-1][1]

    saved = fake_school_assignment.saved[0]
    assert saved[0] == 1  # user_id
    assert saved[3] == 1  # extracted_word_count
    assert saved[5] == 2  # exam_question_count
    assert saved[6] == 1  # exam_correct_count


def test_school_assignment_skips_cards_when_no_words_extracted(monkeypatch):
    fake_users, fake_content, fake_school_assignment, fake_user_words, sent = _wire(monkeypatch)
    telegram_id = "1402"
    _setup_general_user(fake_users, telegram_id)

    async def fake_extract(text, level, max_words):
        return []

    async def fake_analyze(text, level, question_count):
        return ANALYSIS

    monkeypatch.setattr(router.custom_text_extractor, "extract_key_vocabulary", fake_extract)
    monkeypatch.setattr(router.school_assignment_analyzer, "analyze", fake_analyze)

    run(router.handle_update({"message": {"chat": {"id": 1402}, "text": "/수행평가"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1402}, "text": SAMPLE_TEXT}}))

    # 추출된 단어가 없으면 카드 단계 없이 바로 문법해설/예상문제로 넘어간다
    texts = [t for _, t in sent]
    assert any("현재완료" in t for t in texts)
    assert any("예상문제 1" in t for t in texts)


def test_school_assignment_rejects_too_short_text(monkeypatch):
    fake_users, fake_content, fake_school_assignment, fake_user_words, sent = _wire(monkeypatch)
    telegram_id = "1403"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1403}, "text": "/수행평가"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1403}, "text": "짧은글"}}))

    assert "너무 짧습니다" in sent[-1][1]
    assert not fake_school_assignment.saved


def test_school_assignment_falls_back_to_completion_when_no_questions_generated(monkeypatch):
    fake_users, fake_content, fake_school_assignment, fake_user_words, sent = _wire(monkeypatch)
    telegram_id = "1404"
    _setup_general_user(fake_users, telegram_id)

    async def fake_extract(text, level, max_words):
        return []

    async def fake_analyze(text, level, question_count):
        return {"grammar_explanation": "설명만 생성됨", "questions": []}

    monkeypatch.setattr(router.custom_text_extractor, "extract_key_vocabulary", fake_extract)
    monkeypatch.setattr(router.school_assignment_analyzer, "analyze", fake_analyze)

    run(router.handle_update({"message": {"chat": {"id": 1404}, "text": "/수행평가"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1404}, "text": SAMPLE_TEXT}}))

    assert "학교 수행평가 학습 완료" in sent[-1][1]
    saved = fake_school_assignment.saved[0]
    assert saved[5] == 0  # exam_question_count
    assert saved[6] == 0  # exam_correct_count
