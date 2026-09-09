"""개인 맞춤 난이도 시스템(문법): 배치레벨과 무관한 단일 전역 순차 커리큘럼.

버그리포트(2026-09): 예전에는 GRAMMAR_CURRICULUM이 배치레벨(beginner/intermediate/advanced)별로
따로 있어서, "advanced"로 배치된 사용자는 곧바로 그 레벨의 0번 주제(가정법)부터 만났다. 문법
선행지식(예: 가정법 과거완료를 이해하려면 현재완료를 먼저 알아야 함)은 배치레벨과 무관하게 실제로
존재하므로, 배치레벨이 높다고 선행 주제를 건너뛰면 "have p.p.도 모르는데 가정법이 나온다"는 문제가
생긴다. 그래서 전체 학습자가 완전히 동일한 순서 하나를 공유하고, `users.grammar_topic_index`로 그
순서 안에서의 개인 위치만 관리한다. 배치레벨은 이제 "어떤 주제를 보여줄지"에는 전혀 영향을 주지
않는다 — 다음 주제로 넘어가려면 여전히 최소 10문제·정답률 80% 이상(app/difficulty.py)이라는 숙달
기준을 통과해야 하고, 배치레벨이 높은 사용자는 그저 이미 아는 내용이라 빠르게 통과할 뿐이다.

각 항목의 두 번째 값(level)은 노출 순서와 무관한, 콘텐츠 생성/조회 키(app/content/generator.py로
생성되고 grammar_questions 테이블에 그 level로 저장됨)다 — 절대 임의로 바꾸지 말 것.
"""

GRAMMAR_CURRICULUM: list[tuple[str, str]] = [
    ("현재시제", "beginner"),
    ("과거시제", "beginner"),
    ("현재진행형", "beginner"),
    ("미래시제(will/be going to)", "beginner"),
    ("조동사(can/must/should)", "beginner"),
    ("There is/are 구문", "beginner"),
    ("비교급과 최상급", "beginner"),
    ("현재완료", "intermediate"),
    ("과거완료", "intermediate"),
    ("수동태", "intermediate"),
    ("관계대명사", "intermediate"),
    ("조건문(If)", "intermediate"),
    ("분사구문", "intermediate"),
    ("가정법", "advanced"),
    ("도치구문", "advanced"),
    ("강조구문(It is ~ that)", "advanced"),
    ("관계부사", "advanced"),
    ("화법전환(직접화법/간접화법)", "advanced"),
]


def topic_for_index(index: int) -> tuple[str, str] | None:
    """반환값: (topic, level) — level은 콘텐츠뱅크 조회 키. 커리큘럼을 다 마쳤으면 None."""
    if 0 <= index < len(GRAMMAR_CURRICULUM):
        return GRAMMAR_CURRICULUM[index]
    return None


def topic_count() -> int:
    return len(GRAMMAR_CURRICULUM)
