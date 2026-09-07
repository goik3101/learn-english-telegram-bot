def determine_learning_mode(age: int) -> str:
    """기획서 섹션 5: 나이 기반 학습모드 자동 분기."""
    if age <= 10:
        return "CHILD_BEGINNER"
    if age == 11:
        return "CHILD_BRIDGE"
    return "GENERAL"
