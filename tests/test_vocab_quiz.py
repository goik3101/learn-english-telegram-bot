from app.vocab.quiz import build_choices, is_meaning_match


def test_exact_match():
    assert is_meaning_match("사과", "사과")


def test_paraphrase_across_comma_separated_meanings():
    # 실사용 중 발견된 케이스: 정답인데 단순 부분일치로는 오답 처리되던 문제
    correct = "(의도적으로) 모호하게 하다, 애매하게 만들다"
    assert is_meaning_match("모호하게 만들다", correct)


def test_completely_wrong_answer_is_rejected():
    correct = "(의도적으로) 모호하게 하다, 애매하게 만들다"
    assert not is_meaning_match("사과", correct)


def test_empty_answer_is_rejected():
    assert not is_meaning_match("   ", "사과")


def test_substring_of_single_word_meaning_matches():
    assert is_meaning_match("빌리다", "빌리다 (돈이나 물건을)")


def test_build_choices_includes_correct_and_reports_its_index():
    choices, correct_index = build_choices("정답", ["오답1", "오답2", "오답3"])
    assert len(choices) == 4
    assert choices[correct_index] == "정답"
