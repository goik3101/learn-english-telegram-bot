from app.handlers import router
from app.vocab import service as vocab_service
from tests.test_router import FakeUsersRepo, run


class FakeUserWordsRepo:
    def __init__(self, due_rows=None, new_rows=None, learned_rows=None):
        self.due_rows = due_rows or []
        self.new_rows = new_rows or []
        self.learned_rows = learned_rows or []
        self.progress_calls: list[tuple] = []
        self.distractor_pool = ["뜻A", "뜻B", "뜻C"]

    async def get_due_review_words(self, user_id, today):
        return self.due_rows

    async def get_new_words(self, user_id, level, limit):
        return self.new_rows[:limit]

    async def get_distractor_meanings(self, level, exclude_word_id, count):
        return self.distractor_pool[:count]

    async def upsert_word_progress(self, user_id, word_id, status, ease, interval_days, next_review_date):
        self.progress_calls.append((user_id, word_id, status, ease, interval_days, next_review_date))

    async def get_learned_words_sample(self, user_id, limit):
        return self.learned_rows[:limit]


def _word_row(word_id, word, meaning_ko):
    return {
        "word_id": word_id,
        "word": word,
        "meaning_ko": meaning_ko,
        "pronunciation": "/test/",
        "example_sentence": f"This is {word}.",
        "example_translation": "예문입니다.",
        "level": "beginner",
    }


def _wire(monkeypatch, due_rows=None, new_rows=None, learned_rows=None):
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(due_rows=due_rows, new_rows=new_rows, learned_rows=learned_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
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
    return fake_users, fake_user_words, sent


def _setup_general_user(fake_users, telegram_id: str) -> None:
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


def test_vocab_session_known_word_updates_srs_and_advances(monkeypatch):
    new_rows = [_word_row(1, "apple", "사과"), _word_row(2, "book", "책")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "601"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 601}, "text": "/단어학습"}}))
    assert "apple" in sent[-1][1]

    sent.clear()
    run(router.handle_update(_callback_update(601, "vocab:known:1")))

    assert fake_user_words.progress_calls[0][1] == 1
    assert fake_user_words.progress_calls[0][2] == "known"
    assert "book" in sent[-1][1]  # 다음 카드로 넘어감


def test_vocab_session_unknown_word_mcq_then_subjective_correct(monkeypatch):
    new_rows = [_word_row(10, "apple", "사과")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "602"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 602}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(602, "vocab:unknown:10")))
    assert vocab_service.current_stage(telegram_id) == "mcq"

    choices, correct_index = vocab_service.get_mcq(telegram_id)
    assert "사과" in choices

    sent.clear()
    run(router.handle_update(_callback_update(602, f"vocab:mcq:10:{correct_index}")))
    assert "정답입니다" in sent[-1][1]
    assert vocab_service.current_stage(telegram_id) == "subjective"

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 602}, "text": "사과"}}))
    assert "정답입니다" in sent[0][1]
    assert "완료" in sent[-1][1]

    user_id, word_id, status, ease, interval_days, _ = fake_user_words.progress_calls[-1]
    assert (word_id, status) == (10, "learning")
    assert ease == 1.7  # 정답이므로 ease 유지
    assert interval_days == 2  # round(1 * 1.7)


def test_vocab_session_subjective_incorrect_resets_interval_and_lowers_ease(monkeypatch):
    new_rows = [_word_row(20, "apple", "사과")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "603"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 603}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(603, "vocab:unknown:20")))
    choices, correct_index = vocab_service.get_mcq(telegram_id)
    wrong_index = (correct_index + 1) % len(choices)
    run(router.handle_update(_callback_update(603, f"vocab:mcq:20:{wrong_index}")))

    run(router.handle_update({"message": {"chat": {"id": 603}, "text": "완전히 틀린 답"}}))

    user_id, word_id, status, ease, interval_days, _ = fake_user_words.progress_calls[-1]
    assert (word_id, status) == (20, "learning")
    assert ease == 1.5  # 1.7 - 0.2
    assert interval_days == 1  # 오답이므로 리셋


def test_vocab_quiz_flow(monkeypatch):
    learned_rows = [
        {"word_id": 30, "word": "apple", "meaning_ko": "사과", "level": "beginner"},
        {"word_id": 31, "word": "book", "meaning_ko": "책", "level": "beginner"},
    ]
    fake_users, fake_user_words, sent = _wire(monkeypatch, learned_rows=learned_rows)
    telegram_id = "604"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 604}, "text": "/단어시험"}}))
    assert "단어 시험을 시작" in sent[0][1]

    for row in learned_rows:
        # QuizSession은 vocab_service 모듈 내부 상태이므로 직접 조회해 정답 인덱스를 얻는다.
        pass

    # 내부 세션에서 순서대로 정답을 맞춰 진행
    from app.vocab.service import _quiz_sessions  # 화이트박스 검증

    session = _quiz_sessions[telegram_id]
    for item in list(session.items):
        run(router.handle_update(_callback_update(604, f"vocabquiz:{item.word_id}:{item.correct_index}")))

    assert "단어 시험 완료" in sent[-1][1]
    assert "2개 정답" in sent[-1][1]
