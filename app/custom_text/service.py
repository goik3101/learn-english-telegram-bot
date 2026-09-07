from dataclasses import dataclass


@dataclass
class CustomTextSession:
    level: str
    stage: str = "awaiting_text"  # "awaiting_text" | "cards" | "awaiting_translation"
    text: str = ""
    word_count: int = 0


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (다른 학습 세션과 동일한 설계).
_sessions: dict[str, CustomTextSession] = {}


def start(telegram_id: str, level: str) -> None:
    _sessions[telegram_id] = CustomTextSession(level=level)


def is_active(telegram_id: str) -> bool:
    return telegram_id in _sessions


def get_session(telegram_id: str) -> CustomTextSession | None:
    return _sessions.get(telegram_id)


def enter_cards_stage(telegram_id: str, text: str, word_count: int) -> None:
    session = _sessions[telegram_id]
    session.text = text
    session.word_count = word_count
    session.stage = "cards"


def enter_translation_stage(telegram_id: str) -> None:
    _sessions[telegram_id].stage = "awaiting_translation"


def finish(telegram_id: str) -> CustomTextSession:
    return _sessions.pop(telegram_id)
