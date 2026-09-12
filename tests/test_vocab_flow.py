from app.handlers import router
from app.vocab import service as vocab_service
from tests.test_router import FakeUsersRepo, NullGrammarRepo, run


class FakeUserWordsRepo:
    def __init__(self, due_rows=None, new_rows=None, learned_rows=None):
        self.due_rows = due_rows or []
        self.new_rows = new_rows or []
        self.learned_rows = learned_rows or []
        self.progress_calls: list[tuple] = []
        self.distractor_pool = ["뜻A", "뜻B", "뜻C"]
        self.word_attempts: list[tuple] = []
        self.band_results: dict[int, list[bool]] = {}
        self.known_topic_words: list[dict] = []

    async def get_due_review_words(self, user_id, today, limit=None):
        return self.due_rows[:limit] if limit is not None else self.due_rows

    async def get_new_words(self, user_id, level, limit, learning_mode="GENERAL", min_rank=None, max_rank=None):
        return self.new_rows[:limit]

    async def get_learned_word_ids(self, user_id, word_ids):
        return set()  # 테스트 기본값: 아무도 아직 안 배운 상태 — new_rows가 그대로 "신규"로 나옴

    async def get_known_topic_words(self, user_id, topic, level, learning_mode):
        return self.known_topic_words

    async def get_distractor_meanings(self, level, exclude_word_id, count, learning_mode="GENERAL"):
        return self.distractor_pool[:count]

    async def upsert_word_progress(self, user_id, word_id, status, ease, interval_days, next_review_date):
        self.progress_calls.append((user_id, word_id, status, ease, interval_days, next_review_date))

    async def get_learned_words_sample(self, user_id, limit):
        return self.learned_rows[:limit]

    async def record_word_attempt(self, user_id, word_id, band, is_correct):
        self.word_attempts.append((user_id, word_id, band, is_correct))
        self.band_results.setdefault(band, []).insert(0, is_correct)

    async def get_recent_band_results(self, user_id, band, limit):
        return self.band_results.get(band, [])[:limit]


class FakeLearningSessionsRepo:
    """오늘의 주제 통합 학습 테스트용 — learning_sessions을 메모리 dict로 흉내낸다."""

    def __init__(self):
        self.rows: dict[int, dict] = {}

    def _row(self, user_id):
        return self.rows.setdefault(
            user_id,
            {
                "stages_completed": [],
                "today_topic": None,
                "today_topic_word_ids": [],
                "today_reading_passage_id": None,
                "completed_at": None,
            },
        )

    async def start_today(self, user_id):
        self._row(user_id)

    async def get_today_row(self, user_id):
        return self.rows.get(user_id)

    async def mark_stage_complete(self, user_id, stage):
        self._row(user_id)["stages_completed"].append(stage)

    async def set_today_topic(self, user_id, topic, word_ids):
        row = self._row(user_id)
        row["today_topic"] = topic
        row["today_topic_word_ids"] = word_ids

    async def set_today_reading_passage(self, user_id, passage_id):
        self._row(user_id)["today_reading_passage_id"] = passage_id

    async def get_recent_topics(self, user_id, days):
        return []

    async def increment_ai_call_count(self, user_id, by=1):
        pass

    async def mark_completed(self, user_id):
        self._row(user_id)["completed_at"] = "now"


class FakeContentRepo:
    """오늘의 주제 통합 학습 테스트용 — topic_word_rows를 곧바로 "오늘의 주제 단어"로 취급한다
    (기존 new_rows 픽스처를 그대로 오늘의 주제 단어 풀로 재사용)."""

    def __init__(self, topic_word_rows=None):
        self.topic_word_rows = topic_word_rows or []
        self.inserted_words: list[tuple] = []
        self.linked: list[tuple] = []
        self._next_id = 900

    async def get_topic_words(self, topic, level, learning_mode, limit):
        return self.topic_word_rows[:limit]

    async def get_words_by_ids(self, word_ids):
        return [r for r in self.topic_word_rows if r["word_id"] in word_ids]

    async def insert_words(self, level, words, learning_mode="GENERAL"):
        self.inserted_words.append((level, words))
        return len(words)

    async def get_word_ids(self, words, learning_mode="GENERAL"):
        ids = {}
        for w in words:
            ids[w] = self._next_id
            self._next_id += 1
        return ids

    async def insert_topic_words(self, topic, level, learning_mode, word_ids):
        self.linked.append((topic, level, learning_mode, word_ids))

    async def get_frequency_ranks(self, words):
        return {}


class FakeContentGenerator:
    """실제 Gemini 호출을 절대 하지 않는 안전한 기본값 — 테스트 픽스처(topic_word_rows)가 이미
    충분하지 않아도(TOPIC_WORD_MIN 미만) 여기서 빈 목록을 반환해 폴백하게 한다."""

    async def generate_topic_words(self, level, topic, count, learning_mode="GENERAL"):
        return []


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
    fake_learning_sessions = FakeLearningSessionsRepo()
    fake_content = FakeContentRepo(topic_word_rows=new_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "learning_sessions_repo", fake_learning_sessions)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "content_generator", FakeContentGenerator())
    monkeypatch.setattr(router, "grammar_repo", NullGrammarRepo())
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text, parse_mode))

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


def _due_row(word_id, word, meaning_ko):
    return {
        "word_id": word_id,
        "word": word,
        "meaning_ko": meaning_ko,
        "pronunciation": "/test/",
        "example_sentence": f"This is {word}.",
        "example_translation": "예문입니다.",
        "level": "beginner",
        "ease": 1.7,
        "interval_days": 2,
    }


def test_vocab_session_start_message_separates_review_and_new_counts(monkeypatch):
    """버그리포트: 복습(SRS)과 신규(하루 상한)를 하나의 "총 개수"로 합쳐서 보여주면 사용자가
    "신규 단어가 너무 많다"고 오인하게 된다 — 반드시 나눠서 보여줘야 한다."""
    due_rows = [_due_row(50, "run", "달리다"), _due_row(51, "eat", "먹다")]
    new_rows = [_word_row(52, "apple", "사과")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, due_rows=due_rows, new_rows=new_rows)
    telegram_id = "699"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 699}, "text": "/단어학습"}}))

    start_message = sent[0][1]
    assert "복습 2개" in start_message
    assert "신규 1개" in start_message
    assert "총 3개" in start_message


def test_word_card_shows_meaning_and_mnemonic_and_emoji_immediately(monkeypatch):
    """사용자 피드백(기억연구 근거): 첫 노출 때 맨입으로 추측시키는 건 효과가 낮으므로, 카드를
    처음 보여줄 때부터 뜻/발음/예문/연상법/이모지를 곧바로 전부 노출해야 한다(추측 단계 없음)."""
    row = _word_row(60, "apple", "사과")
    row["mnemonic"] = "1단계(소리): '애플'은 '아파'처럼 들림. 2단계(이미지): 사과를 먹다가 배가 아파오는 장면을 상상해보세요."
    row["emoji"] = "🍎"
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=[row])
    telegram_id = "606"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 606}, "text": "/단어학습"}}))
    card_text = sent[-1][1]
    assert "apple" in card_text
    assert "사과" in card_text
    assert "아파" in card_text
    assert "🍎" in card_text
    assert vocab_service.current_stage(telegram_id) == "card"


def test_session_summary_lists_new_words_learned(monkeypatch):
    new_rows = [_word_row(61, "apple", "사과"), _word_row(62, "book", "책")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "607"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 607}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(607, "vocab:known:61")))
    sent.clear()
    run(router.handle_update(_callback_update(607, "vocab:known:62")))

    summary_text = sent[-1][1]
    assert "오늘 배운 신규 단어" in summary_text
    assert "apple" in summary_text
    assert "book" in summary_text


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


def test_subjective_wrong_answer_reshows_mnemonic(monkeypatch):
    """사용자 피드백(암기법 연구): 오답 시 정답만 알려주지 말고 연상법을 재노출해 그 자리에서
    재학습되게 해야 한다."""
    row = _word_row(22, "apple", "사과")
    row["mnemonic"] = "1단계(소리): '애플'은 '아파'처럼 들림. 2단계(이미지): 사과를 먹다가 배가 아파오는 장면."
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=[row])
    telegram_id = "608"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 608}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(608, "vocab:unknown:22")))
    choices, correct_index = vocab_service.get_mcq(telegram_id)
    wrong_index = (correct_index + 1) % len(choices)
    run(router.handle_update(_callback_update(608, f"vocab:mcq:22:{wrong_index}")))

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 608}, "text": "완전히 틀린 답"}}))

    assert "아파" in sent[0][1]


def test_vocab_mcq_wrong_answer_hides_reveal_behind_spoiler(monkeypatch):
    new_rows = [_word_row(21, "apple", "사과")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "605"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 605}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(605, "vocab:unknown:21")))
    choices, correct_index = vocab_service.get_mcq(telegram_id)
    wrong_index = (correct_index + 1) % len(choices)

    sent.clear()
    run(router.handle_update(_callback_update(605, f"vocab:mcq:21:{wrong_index}")))

    chat_id, text, parse_mode = sent[-1]
    assert parse_mode == "HTML"
    assert 'class="tg-spoiler"' in text
    # 스포일러 태그 밖의 일반 텍스트에는 정답(뜻)이 그대로 노출되면 안 된다.
    plain_text = text.split('<span class="tg-spoiler">')[0]
    assert choices[correct_index] not in plain_text
    assert "직접 입력해보세요" in text


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
