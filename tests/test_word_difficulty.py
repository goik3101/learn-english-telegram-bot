from app import difficulty
from app.handlers import router
from app.vocab import frequency as word_frequency
from tests.test_router import FakeUsersRepo, run
from tests.test_vocab_flow import FakeUserWordsRepo, _setup_general_user, _word_row


def test_band_range_returns_expected_boundaries():
    assert word_frequency.band_range(0) == (1, 1000)
    assert word_frequency.band_range(5) == (8001, 999_999)


def test_band_range_clamps_out_of_range_band():
    assert word_frequency.band_range(-1) == word_frequency.band_range(0)
    assert word_frequency.band_range(99) == word_frequency.band_range(word_frequency.MAX_WORD_BAND)


def test_next_band_holds_below_minimum_sample_size():
    # 9개만 있으면 100% 정답이어도 아직 조정하지 않는다(최소 학습량 미달).
    results = [True] * 9
    assert difficulty.next_band(2, results, min_band=0, max_band=5) == 2


def test_next_band_advances_on_high_accuracy():
    results = [True] * 9 + [False]  # 최근 10개 중 9개 정답 = 90%
    assert difficulty.next_band(2, results, min_band=0, max_band=5) == 3


def test_next_band_regresses_on_low_accuracy():
    results = [False] * 6 + [True] * 4  # 최근 10개 중 4개 정답 = 40%
    assert difficulty.next_band(2, results, min_band=0, max_band=5) == 1


def test_next_band_holds_in_middle_range():
    results = [True] * 6 + [False] * 4  # 60% — advance(80%)도 regress(50%)도 아님
    assert difficulty.next_band(2, results, min_band=0, max_band=5) == 2


def test_next_band_respects_min_and_max_bounds():
    assert difficulty.next_band(0, [False] * 10, min_band=0, max_band=5) == 0
    assert difficulty.next_band(5, [True] * 10, min_band=0, max_band=5) == 5


def test_next_band_uses_only_most_recent_window():
    # 오래된 기록이 섞여 있어도 앞의 10개(최신순으로 정렬되어 들어온다고 가정)만 본다.
    results = [True] * 10 + [False] * 20
    assert difficulty.next_band(2, results, min_band=0, max_band=5) == 3


# --- 라우터 통합: 신규 단어 완료 시 밴드 기록/조정 ---


def _wire(monkeypatch, new_rows=None):
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(new_rows=new_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
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
    return fake_users, fake_user_words, sent


def _callback_update(telegram_id: int, data: str) -> dict:
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": telegram_id},
            "message": {"chat": {"id": telegram_id}},
            "data": data,
        }
    }


def test_known_click_on_new_word_records_band_attempt(monkeypatch):
    new_rows = [_word_row(801, "apple", "사과")]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "8001"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 8001}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(8001, "vocab:known:801")))

    assert fake_user_words.word_attempts == [(1, 801, 0, True)]


def test_word_band_advances_after_ten_correct_new_words(monkeypatch):
    new_rows = [_word_row(900 + i, f"word{i}", f"뜻{i}") for i in range(10)]
    fake_users, fake_user_words, sent = _wire(monkeypatch, new_rows=new_rows)
    telegram_id = "8002"
    _setup_general_user(fake_users, telegram_id)
    fake_users.users[telegram_id]["daily_new_word_limit"] = 10  # 10개 전부 한 세션 큐에 담기게

    run(router.handle_update({"message": {"chat": {"id": 8002}, "text": "/단어학습"}}))
    for i in range(10):
        run(router.handle_update(_callback_update(8002, f"vocab:known:{900 + i}")))

    assert fake_users.users[telegram_id]["word_band"] == 1


def test_word_band_does_not_change_for_due_review_words(monkeypatch):
    due_rows = [
        {
            "word_id": 950,
            "word": "review",
            "meaning_ko": "복습",
            "pronunciation": "/rɪˈvjuː/",
            "example_sentence": "Time to review.",
            "example_translation": "복습할 시간.",
            "level": "beginner",
            "ease": 1.7,
            "interval_days": 2,
        }
    ]
    fake_users = FakeUsersRepo()
    fake_user_words = FakeUserWordsRepo(due_rows=due_rows)
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        pass

    async def fake_answer_cb(callback_query_id, text=None):
        pass

    async def fake_delete_message(chat_id, message_id):
        pass

    monkeypatch.setattr(router, "send_message", fake_send)
    monkeypatch.setattr(router, "answer_callback_query", fake_answer_cb)
    monkeypatch.setattr(router, "delete_message", fake_delete_message)

    telegram_id = "8003"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 8003}, "text": "/단어학습"}}))
    run(router.handle_update(_callback_update(8003, "vocab:known:950")))

    assert fake_user_words.word_attempts == []  # 복습 단어는 밴드 통계 대상이 아님


def test_vocab_queue_falls_back_when_band_has_no_candidates(monkeypatch):
    # get_new_words가 밴드 필터(1차 호출)에서는 빈 목록을, 폴백(2차 호출, min_rank=None)에서는
    # 결과를 주는 상황을 시뮬레이션한다.
    calls: list[tuple] = []
    fallback_rows = [_word_row(999, "fallback", "폴백")]

    class FallbackRepo(FakeUserWordsRepo):
        async def get_new_words(self, user_id, level, limit, learning_mode="GENERAL", min_rank=None, max_rank=None):
            calls.append((min_rank, max_rank))
            if min_rank is not None:
                return []
            return fallback_rows[:limit]

    fake_users = FakeUsersRepo()
    fake_user_words = FallbackRepo()
    monkeypatch.setattr(router, "users_repo", fake_users)
    monkeypatch.setattr(router, "user_words_repo", fake_user_words)
    monkeypatch.setattr(router, "db_available", lambda: True)

    sent: list[tuple] = []

    async def fake_send(chat_id, text, reply_markup=None, parse_mode=None):
        sent.append((chat_id, text))

    monkeypatch.setattr(router, "send_message", fake_send)

    telegram_id = "8004"
    _setup_general_user(fake_users, telegram_id)

    run(router.handle_update({"message": {"chat": {"id": 8004}, "text": "/단어학습"}}))

    assert len(calls) == 2
    assert calls[0][0] is not None  # 1차: 밴드 필터
    assert calls[1] == (None, None)  # 2차: 폴백(필터 없음)
    assert "fallback" in sent[-1][1]
