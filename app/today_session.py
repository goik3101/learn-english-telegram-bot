"""오늘의 학습(M7 Planner): 단어->문법->해석->회화를 확인질문 없이 자동으로 이어준다 (섹션7/8-2 학습자동화 원칙).

소수 사용자 규모(섹션3-2)를 고려해 세션 상태는 프로세스 메모리로만 관리한다(다른 학습 세션들과 동일한 설계).
"""

STAGES = ["vocab", "grammar", "reading", "conversation"]

_active: dict[str, int] = {}


def start(telegram_id: str) -> str:
    _active[telegram_id] = 0
    return STAGES[0]


def is_active(telegram_id: str) -> bool:
    return telegram_id in _active


def current_stage(telegram_id: str) -> str | None:
    idx = _active.get(telegram_id)
    return STAGES[idx] if idx is not None else None


def advance(telegram_id: str) -> str | None:
    """다음 단계 이름을 반환. 더 이상 없으면 세션을 종료하고 None을 반환."""
    idx = _active.get(telegram_id)
    if idx is None:
        return None
    idx += 1
    if idx >= len(STAGES):
        del _active[telegram_id]
        return None
    _active[telegram_id] = idx
    return STAGES[idx]
