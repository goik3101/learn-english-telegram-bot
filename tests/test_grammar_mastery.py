from app.grammar import mastery


def test_count_consecutive_wrong_counts_from_the_most_recent():
    assert mastery.count_consecutive_wrong([False, False, True, False]) == 2


def test_count_consecutive_wrong_is_zero_when_most_recent_is_correct():
    assert mastery.count_consecutive_wrong([True, False, False]) == 0


def test_count_consecutive_wrong_handles_empty_list():
    assert mastery.count_consecutive_wrong([]) == 0


def test_count_consecutive_wrong_counts_all_if_never_correct():
    assert mastery.count_consecutive_wrong([False, False, False]) == 3
