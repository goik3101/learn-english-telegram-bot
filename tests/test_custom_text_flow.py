from app.handlers import router
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user


class FakeContentRepo:
    def __init__(self):
        self.inserted_words: list[tuple] = []
        self._next_id = 500

    async def insert_words(self, level, words):
        self.inserted_words.append((level, words))
        return len(words)

    async def get_word_ids(self, words):
        ids = {}
        for w in words:
            ids[w] = self._next_id
            self._next_id += 1
        return ids


class FakeCustomTextRepo:
    def __init__(self):
        self.saved: list[tuple] = []

    async def save(self, user_id, level, source_text, extracted_word_count, user_translation, ai_feedback):
        self.saved.append((user_id, level, source_text, extracted_word_count, user_translation, ai_feedback))


def _wire(monkeypatch):
    fake_users = FakeUsersRepo()
    fake_content = FakeContentRepo()
    fake_custom_text = FakeCustomTextRepo()
    fake_user_words = FakeUserWordsRepo()

    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "content_repo", fake_content)
    monkeypatch.setattr(router, "custom_text_repo", fake_custom_text)
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
    return fake_users, fake_content, fake_custom_text, fake_user_words, sent


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


def test_custom_text_full_flow_with_extracted_word(monkeypatch):
    fake_users, fake_content, fake_custom_text, fake_user_words, sent = _wire(monkeypatch)
    telegram_id = "1301"
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

    async def fake_feedback(text, translation):
        return "핵심을 잘 짚으셨어요!"

    monkeypatch.setattr(router.custom_text_extractor, "extract_key_vocabulary", fake_extract)
    monkeypatch.setattr(router.custom_text_feedback, "generate_feedback", fake_feedback)

    run(router.handle_update({"message": {"chat": {"id": 1301}, "text": "/텍스트학습"}}))
    assert "붙여넣어" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1301}, "text": SAMPLE_TEXT}}))
    assert "ubiquitous" in sent[-1][1]
    assert fake_content.inserted_words[0][0] == "beginner"

    sent.clear()
    run(router.handle_update(_callback_update(1301, "vocab:known:500")))
    assert "한국어로 해석" in sent[-1][1]
    assert SAMPLE_TEXT in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1301}, "text": "스마트폰은 어디에나 있다."}}))
    assert "핵심을 잘 짚으셨어요" in sent[-1][1]
    assert "완료" in sent[-1][1]

    saved = fake_custom_text.saved[0]
    assert saved[0] == 1  # user_id
    assert saved[3] == 1  # extracted_word_count
    assert saved[4] == "스마트폰은 어디에나 있다."


def test_custom_text_skips_cards_when_no_words_extracted(monkeypatch):
    fake_users, fake_content, fake_custom_text, fake_user_words, sent = _wire(monkeypatch)
    telegram_id = "1302"
    _setup_general_user(fake_users, telegram_id)

    async def fake_extract(text, level, max_words):
        return []

    async def fake_feedback(text, translation):
        return "좋아요!"

    monkeypatch.setattr(router.custom_text_extractor, "extract_key_vocabulary", fake_extract)
    monkeypatch.setattr(router.custom_text_feedback, "generate_feedback", fake_feedback)

    run(router.handle_update({"message": {"chat": {"id": 1302}, "text": "/텍스트학습"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1302}, "text": SAMPLE_TEXT}}))

    # 추출된 단어가 없으면 카드 단계 없이 바로 해석 요청으로 넘어간다
    assert "한국어로 해석" in sent[-1][1]

    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1302}, "text": "내 나름의 해석"}}))
    assert "완료" in sent[-1][1]


def test_custom_text_rejects_too_short_text(monkeypatch):
    fake_users, fake_content, fake_custom_text, fake_user_words, sent = _wire(monkeypatch)
    telegram_id = "1303"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 1303}, "text": "/텍스트학습"}}))
    sent.clear()
    run(router.handle_update({"message": {"chat": {"id": 1303}, "text": "짧은글"}}))

    assert "너무 짧습니다" in sent[-1][1]
    assert not fake_custom_text.saved
