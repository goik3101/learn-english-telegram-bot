from app.vocab import level


def test_new_user_with_no_mastered_words_defaults_to_beginner():
    assert level.level_from_mastered_words(None, 0) == "beginner"


def test_few_mastered_words_stays_beginner_even_if_rank_is_high():
    """표본이 충분히 쌓이기 전에는 우연히 어려운 단어 몇 개를 맞혔다고 레벨을 올리지 않는다."""
    assert level.level_from_mastered_words(6000, level.MIN_MASTERED_WORDS_FOR_ESTIMATE - 1) == "beginner"


def test_enough_low_rank_mastered_words_stays_beginner():
    assert level.level_from_mastered_words(1000, level.MIN_MASTERED_WORDS_FOR_ESTIMATE) == "beginner"


def test_enough_mid_rank_mastered_words_is_intermediate():
    assert level.level_from_mastered_words(3500, level.MIN_MASTERED_WORDS_FOR_ESTIMATE) == "intermediate"


def test_enough_high_rank_mastered_words_is_advanced():
    assert level.level_from_mastered_words(7000, level.MIN_MASTERED_WORDS_FOR_ESTIMATE) == "advanced"
