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

MIN_MASTERED_WORDS_FOR_ESTIMATE = 15

# app/vocab/frequency.py의 6단계 frequency_rank 밴드 경계를 재사용해 3단계 레벨 문자열에 맞춘다.
BEGINNER_MAX_RANK = 2000
INTERMEDIATE_MAX_RANK = 5000


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
