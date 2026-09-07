from dataclasses import dataclass, field

MAX_TURNS = 5  # 섹션3-1: 텍스트로 AI와 5턴 대화 연습


@dataclass
class ConversationSession:
    level: str
    session_id: int
    history: list[tuple[str, str]] = field(default_factory=list)  # ("ai"|"user", text)
    turn_count: int = 0


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (다른 학습 세션과 동일한 설계).
_sessions: dict[str, ConversationSession] = {}


def start(telegram_id: str, level: str, session_id: int) -> ConversationSession:
    session = ConversationSession(level=level, session_id=session_id)
    _sessions[telegram_id] = session
    return session


def is_active(telegram_id: str) -> bool:
    return telegram_id in _sessions


def get_session(telegram_id: str) -> ConversationSession | None:
    return _sessions.get(telegram_id)


def add_ai_message(telegram_id: str, text: str) -> None:
    _sessions[telegram_id].history.append(("ai", text))


def add_user_turn(telegram_id: str, user_text: str, ai_text: str) -> int:
    session = _sessions[telegram_id]
    session.history.append(("user", user_text))
    session.history.append(("ai", ai_text))
    session.turn_count += 1
    return session.turn_count


def finish(telegram_id: str) -> ConversationSession:
    return _sessions.pop(telegram_id)
