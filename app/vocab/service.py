from dataclasses import dataclass, field


@dataclass(frozen=True)
class WordItem:
    word_id: int
    word: str
    meaning_ko: str
    pronunciation: str | None
    example_sentence: str | None
    example_translation: str | None
    level: str
    ease: float
    interval_days: int
    is_new: bool
    learning_mode: str = "GENERAL"
    mnemonic: str | None = None
    example_sentences: list[dict] | None = None  # [{"sentence":..,"translation":..}, ...] — 복습회차마다 다른 예문
    review_count: int = 0
    emoji: str | None = None
    mastery: str = "new"  # app.vocab.mastery 참고 — 학습단계(learning steps) 상태머신의 현재 위치
    consecutive_correct: int = 0


def pick_example(item: WordItem) -> tuple[str | None, str | None]:
    """사용자 피드백(단어 암기): 복습 회차마다 같은 예문만 반복되지 않도록, 여러 예문이 있으면
    review_count로 순환시켜 고른다. 예문이 하나뿐이거나(과거 데이터) 없으면 기존 단일 컬럼 그대로."""
    examples = item.example_sentences
    if examples:
        chosen = examples[item.review_count % len(examples)]
        return chosen.get("sentence"), chosen.get("translation")
    return item.example_sentence, item.example_translation


@dataclass
class VocabSession:
    queue: list[WordItem]
    index: int = 0
    stage: str = "card"  # "card" | "mcq" | "subjective"
    mcq_choices: list[str] = field(default_factory=list)
    mcq_correct_index: int = 0
    reviewed: int = 0
    correct: int = 0
    new_words_seen: list[tuple[str, str]] = field(default_factory=list)  # (word, meaning_ko) — 세션 종료 요약용


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (레벨진단과 동일한 설계 결정).
_sessions: dict[str, VocabSession] = {}


def start_session(telegram_id: str, items: list[WordItem]) -> WordItem | None:
    _sessions[telegram_id] = VocabSession(queue=items)
    return current_item(telegram_id)


def has_session(telegram_id: str) -> bool:
    return telegram_id in _sessions


def current_item(telegram_id: str) -> WordItem | None:
    session = _sessions.get(telegram_id)
    if session is None or session.index >= len(session.queue):
        return None
    return session.queue[session.index]


def current_stage(telegram_id: str) -> str | None:
    session = _sessions.get(telegram_id)
    return session.stage if session else None


def enter_mcq_stage(telegram_id: str, choices: list[str], correct_index: int) -> None:
    session = _sessions[telegram_id]
    session.stage = "mcq"
    session.mcq_choices = choices
    session.mcq_correct_index = correct_index


def get_mcq(telegram_id: str) -> tuple[list[str], int]:
    session = _sessions[telegram_id]
    return session.mcq_choices, session.mcq_correct_index


def enter_subjective_stage(telegram_id: str) -> None:
    _sessions[telegram_id].stage = "subjective"


def record_result(telegram_id: str, is_correct: bool) -> None:
    session = _sessions[telegram_id]
    session.reviewed += 1
    if is_correct:
        session.correct += 1


@dataclass(frozen=True)
class SessionSummary:
    reviewed: int
    correct: int
    new_words: list[tuple[str, str]]


def advance(telegram_id: str) -> WordItem | None:
    session = _sessions[telegram_id]
    current = current_item(telegram_id)
    if current is not None and current.is_new:
        session.new_words_seen.append((current.word, current.meaning_ko))
    session.index += 1
    session.stage = "card"
    return current_item(telegram_id)


def finish_session(telegram_id: str) -> SessionSummary:
    session = _sessions.pop(telegram_id)
    return SessionSummary(reviewed=session.reviewed, correct=session.correct, new_words=session.new_words_seen)


# --- 단어시험(/단어시험): 이미 배운 단어 중 샘플로 객관식 테스트, SRS에는 영향 없음 ---


@dataclass(frozen=True)
class QuizItem:
    word_id: int
    word: str
    choices: list[str]
    correct_index: int


@dataclass
class QuizSession:
    items: list[QuizItem]
    index: int = 0
    correct: int = 0


_quiz_sessions: dict[str, QuizSession] = {}


def start_quiz(telegram_id: str, items: list[QuizItem]) -> QuizItem | None:
    _quiz_sessions[telegram_id] = QuizSession(items=items)
    return items[0] if items else None


def is_quiz_active(telegram_id: str) -> bool:
    return telegram_id in _quiz_sessions


def abandon_quiz(telegram_id: str) -> None:
    _quiz_sessions.pop(telegram_id, None)


def abandon_session(telegram_id: str) -> None:
    """/학습중단: 이미 답한 카드는 매 답변마다 즉시 SRS에 반영됐으므로, 남은 카드만 버린다."""
    _sessions.pop(telegram_id, None)


@dataclass(frozen=True)
class QuizAnswerResult:
    finished: bool
    next_item: QuizItem | None = None
    correct: int = 0
    total: int = 0


def submit_quiz_answer(telegram_id: str, word_id: int, choice_index: int) -> QuizAnswerResult | None:
    session = _quiz_sessions.get(telegram_id)
    if session is None or session.index >= len(session.items):
        return None

    item = session.items[session.index]
    if item.word_id != word_id:
        return None  # 이미 지나간 문항에 대한 응답 (stale callback)

    if choice_index == item.correct_index:
        session.correct += 1
    session.index += 1

    if session.index < len(session.items):
        return QuizAnswerResult(finished=False, next_item=session.items[session.index])

    total = len(session.items)
    correct = session.correct
    del _quiz_sessions[telegram_id]
    return QuizAnswerResult(finished=True, correct=correct, total=total)
