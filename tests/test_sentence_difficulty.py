from app.content import sentence_difficulty


def test_short_simple_sentence_passes():
    text = "I like my dog. My dog is happy. We play every day."
    limits = sentence_difficulty.limits_for_level("beginner")
    result = sentence_difficulty.validate(text, ["dog", "happy", "play"], limits)
    assert result.passed
    assert result.violations == []


def test_overly_long_sentence_is_flagged():
    text = (
        "I woke up early in the morning and decided that I would go to the park "
        "with my dog because the weather was so nice and sunny today."
    )
    limits = sentence_difficulty.limits_for_level("beginner")
    result = sentence_difficulty.validate(text, ["dog", "park"], limits)
    assert not result.passed
    assert any("너무 깁니다" in v for v in result.violations)


def test_too_many_unknown_words_is_flagged():
    text = (
        "Ubiquitous algorithmic accountability mechanisms necessitate pragmatic "
        "epistemological considerations."
    )
    limits = sentence_difficulty.limits_for_level("beginner")
    result = sentence_difficulty.validate(text, ["dog", "happy", "play"], limits)
    assert not result.passed
    assert any("단어 목록 밖" in v for v in result.violations)


def test_limits_scale_with_level():
    beginner = sentence_difficulty.limits_for_level("beginner")
    intermediate = sentence_difficulty.limits_for_level("intermediate")
    advanced = sentence_difficulty.limits_for_level("advanced")
    assert beginner.max_words_per_sentence < intermediate.max_words_per_sentence < advanced.max_words_per_sentence


def test_unknown_level_falls_back_to_beginner_limits():
    assert sentence_difficulty.limits_for_level("nonsense") == sentence_difficulty.limits_for_level("beginner")


def test_longest_sentence_word_count_picks_the_longest_of_several():
    text = "Short one. This one has quite a few more words in it than the first one did."
    count = sentence_difficulty.longest_sentence_word_count(text)
    assert count == len(
        "This one has quite a few more words in it than the first one did".split()
    )
