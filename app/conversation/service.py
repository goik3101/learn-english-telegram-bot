from dataclasses import dataclass, field

MAX_TURNS = 5  # 섹션3-1: 텍스트로 AI와 5턴 대화 연습


@dataclass
class ConversationSession:
    level: str
    session_id: int
    topic: str | None = None
    preview_words: list[str] = field(default_factory=list)
    history: list[tuple[str, str]] = field(default_factory=list)  # ("ai"|"user", text)
    turn_count: int = 0


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (다른 학습 세션과 동일한 설계).
_sessions: dict[str, ConversationSession] = {}


def start(
    telegram_id: str, level: str, session_id: int, topic: str | None = None, preview_words: list[str] | None = None
) -> ConversationSession:
    session = ConversationSession(level=level, session_id=session_id, topic=topic, preview_words=preview_words or [])
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


# --- 회화 사전 단어학습: 오늘의 주제 단어카드를 먼저 학습시키는 동안, 회화 시작에 필요한
# 정보(레벨/주제/단어id)를 잠깐 들고 있는 대기 상태. 단어카드 학습(app.vocab.service)이 끝나면
# app.handlers.router._finish_vocab_word가 이 대기 상태를 감지해 실제 회화를 시작한다.


@dataclass(frozen=True)
class ConversationPreview:
    level: str
    topic: str
    word_rows: list[dict]  # content_repo.get_topic_words()가 반환하는 형태 그대로 보관


_previews: dict[str, ConversationPreview] = {}


def start_preview(telegram_id: str, level: str, topic: str, word_rows: list[dict]) -> None:
    _previews[telegram_id] = ConversationPreview(level=level, topic=topic, word_rows=word_rows)


def get_preview(telegram_id: str) -> ConversationPreview | None:
    return _previews.get(telegram_id)


def pop_preview(telegram_id: str) -> ConversationPreview | None:
    return _previews.pop(telegram_id, None)
