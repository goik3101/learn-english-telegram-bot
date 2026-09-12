from app.vocab import mastery


def test_first_correct_answer_does_not_jump_straight_to_mastered():
    transition = mastery.apply_answer(mastery.MASTERY_NEW, 0, is_correct=True)
    assert transition.mastery == mastery.MASTERY_STEP_2
    assert transition.consecutive_correct == 1
    assert transition.is_learning_step is True  # 정규 SRS 간격 성장 아직 시작 안 함


def test_second_correct_answer_graduates_to_review():
    transition = mastery.apply_answer(mastery.MASTERY_STEP_2, 1, is_correct=True)
    assert transition.mastery == mastery.MASTERY_REVIEW
    assert transition.consecutive_correct == 2
    assert transition.is_learning_step is False  # 이제부터 ease 기반 정규 간격 성장


def test_repeated_correct_in_review_eventually_becomes_mastered():
    transition = mastery.apply_answer(mastery.MASTERY_REVIEW, mastery.MASTERED_STREAK - 1, is_correct=True)
    assert transition.mastery == mastery.MASTERY_MASTERED
    assert transition.consecutive_correct == mastery.MASTERED_STREAK


def test_correct_in_review_before_streak_threshold_stays_review():
    transition = mastery.apply_answer(mastery.MASTERY_REVIEW, 0, is_correct=True)
    assert transition.mastery == mastery.MASTERY_REVIEW
    assert transition.consecutive_correct == 1


def test_wrong_answer_resets_to_learning_step_1_regardless_of_prior_stage():
    for prior in (mastery.MASTERY_NEW, mastery.MASTERY_STEP_1, mastery.MASTERY_STEP_2,
                  mastery.MASTERY_REVIEW, mastery.MASTERY_MASTERED):
        transition = mastery.apply_answer(prior, 5, is_correct=False)
        assert transition.mastery == mastery.MASTERY_STEP_1
        assert transition.consecutive_correct == 0
        assert transition.is_learning_step is True


def test_wrong_answer_after_mastered_does_not_erase_all_history_to_new():
    """오답이어도 완전히 처음(new)으로 되돌리지 않는다 — 한 번은 노출됐다는 사실 자체는 유효하다."""
    transition = mastery.apply_answer(mastery.MASTERY_MASTERED, 10, is_correct=False)
    assert transition.mastery != mastery.MASTERY_NEW
    assert transition.mastery == mastery.MASTERY_STEP_1
