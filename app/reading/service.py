from dataclasses import dataclass

MAX_ATTEMPTS = 2  # 힌트(1회) -> 채점+정답공개(최대 2회째) — 섹션3-1 "정답 먼저 제공 안 함" 원칙의 축소 구현


@dataclass(frozen=True)
class Passage:
    passage_id: int
    text: str
    model_translation: str
    level: str


@dataclass
class ReadingSession:
    passage: Passage
    is_review: bool
    attempt: int = 0


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (다른 학습 세션과 동일한 설계).
_sessions: dict[str, ReadingSession] = {}


def start(telegram_id: str, passage: Passage, is_review: bool) -> None:
    _sessions[telegram_id] = ReadingSession(passage=passage, is_review=is_review)


def is_active(telegram_id: str) -> bool:
    return telegram_id in _sessions


def get_session(telegram_id: str) -> ReadingSession | None:
    return _sessions.get(telegram_id)


def record_attempt(telegram_id: str) -> int:
    session = _sessions[telegram_id]
    session.attempt += 1
    return session.attempt


def finish(telegram_id: str) -> ReadingSession:
    return _sessions.pop(telegram_id)
