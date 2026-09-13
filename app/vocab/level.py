"""V2 학습 엔진: 어휘 레벨(vocabulary level)을 문법 진행도와 완전히 분리해서 독립적으로 추정한다.

기존에는 단어 신규 콘텐츠 생성에 쓰는 레벨 문자열("beginner"/"intermediate"/"advanced")을
`_get_effective_content_level`(app/handlers/router.py) 하나로 문법 진행도에서만 유도했다 —
그 결과 "어휘는 약한데 문법은 중간" 같은 사용자를 표현할 방법이 없었다(사용자 요청: 영역별
독립 축).

frequency_rank는 요청사항대로 보조자료로만 쓴다 — 우선순위는 이 사용자가 실제로 mastered
상태까지 확인한 단어들의 frequency_rank 분포다("빈도가 높아서 쉽다"가 아니라 "이 사용자가
실제로 이 정도 빈도의 단어까지는 확실히 안다"를 근거로 삼는다는 점에서 실제 학습 기록 우선
원칙을 지킨다). mastered 단어가 충분히 쌓이기 전에는 기본값 "beginner"로 시작한다(요청사항:
기본값은 쉬운 고교 기본 영어, 난이도 상승은 실제 성취 데이터가 충분할 때만).
"""

from app.vocab import frequency as word_frequency

MIN_MASTERED_WORDS_FOR_ESTIMATE = 15

# app/vocab/frequency.py의 6단계 frequency_rank 밴드 경계를 재사용해 3단계 레벨 문자열에 맞춘다.
BEGINNER_MAX_RANK = 2000
INTERMEDIATE_MAX_RANK = 5000

# 신규/기존 단어를 하나의 서수로 비교하기 위한 순서(복습 우선순위 조정, get_due_review_words 참고).
LEVEL_ORDER = {"beginner": 0, "intermediate": 1, "advanced": 2}


def level_from_mastered_words(median_frequency_rank: float | None, mastered_count: int) -> str:
    """median_frequency_rank: mastered 단어들의 frequency_rank 중앙값(없으면 None).
    mastered_count: frequency_rank가 있는 mastered 단어 수(표본 크기 확인용)."""
    if mastered_count < MIN_MASTERED_WORDS_FOR_ESTIMATE or median_frequency_rank is None:
        return "beginner"
    if median_frequency_rank <= BEGINNER_MAX_RANK:
        return "beginner"
    if median_frequency_rank <= INTERMEDIATE_MAX_RANK:
        return "intermediate"
    return "advanced"


# 신규 단어 생성 검증(word-level validator): 실사용 사례("subsidiary" 등 GRE급 단어가 beginner
# 요청에서 나온 사고) 반영 — AI가 자체 보고하는 frequency_rank를 무조건 신뢰하지 않고, 요청한
# level과 명백히 안 맞으면(코드 레벨에서) 걸러낸다. 각 레벨에 실제보다 넉넉한 밴드를 허용해
# 경계에 걸친 단어까지 무리하게 reject하지 않도록 보수적으로 설계한다.
LEVEL_MAX_BAND = {
    "beginner": 3,  # frequency_rank <= 5000까지 허용
    "intermediate": 4,  # frequency_rank <= 8000까지 허용
    "advanced": word_frequency.MAX_WORD_BAND,  # 사실상 무제한(advanced는 희귀 단어도 허용)
}


def band_for_rank(frequency_rank: int) -> int:
    for band, (lo, hi) in enumerate(word_frequency.WORD_FREQUENCY_BANDS):
        if lo <= frequency_rank <= hi:
            return band
    return word_frequency.MAX_WORD_BAND


def is_word_too_hard_for_level(frequency_rank: int | None, level: str) -> bool:
    """생성된 단어의 frequency_rank가 요청한 level에 명백히 안 맞는지 판단한다(보수적 —
    경계에 걸친 단어는 통과시킨다). frequency_rank가 없으면(AI가 못 주거나 파싱 실패) 판단을
    보류하고 통과시킨다 — frequency_rank 부재만으로 정상 단어를 깨뜨리지 않기 위함."""
    if frequency_rank is None:
        return False
    max_band = LEVEL_MAX_BAND.get(level, word_frequency.MAX_WORD_BAND)
    return band_for_rank(frequency_rank) > max_band
