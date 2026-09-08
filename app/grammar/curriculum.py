"""개인 맞춤 난이도 시스템(문법): 레벨별 고정 학습 순서.

placement/questions.py, child_beginner/curriculum.py와 동일하게 코드에 정적 데이터로 둔다 —
순서가 바뀔 일이 거의 없고, DB 테이블+시딩 스크립트를 따로 두는 것보다 훨씬 단순하다.
`/문법학습`(신규 세트)은 이 순서를 따라가며 한 주제를 충분히 익혀야(최소 10문제, 정답률 80%)
다음 주제로 진행한다. `/복습`은 이 순서와 무관하게 취약 주제를 가중해서 출제한다.
"""

GRAMMAR_CURRICULUM: dict[str, list[str]] = {
    "beginner": [
        "현재시제",
        "과거시제",
        "현재진행형",
        "미래시제(will/be going to)",
        "조동사(can/must/should)",
        "There is/are 구문",
        "비교급과 최상급",
    ],
    "intermediate": [
        "현재완료",
        "과거완료",
        "수동태",
        "관계대명사",
        "조건문(If)",
        "분사구문",
    ],
    "advanced": [
        "가정법",
        "도치구문",
        "강조구문(It is ~ that)",
        "관계부사",
        "화법전환(직접화법/간접화법)",
    ],
}


def topic_for_index(level: str, index: int) -> str | None:
    topics = GRAMMAR_CURRICULUM.get(level, [])
    if 0 <= index < len(topics):
        return topics[index]
    return None


def topic_count(level: str) -> int:
    return len(GRAMMAR_CURRICULUM.get(level, []))
