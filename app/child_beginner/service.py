from dataclasses import dataclass, field
from typing import Union

from app.child_beginner.curriculum import LetterCard, PhonicsCard

Card = Union[LetterCard, PhonicsCard]


@dataclass(frozen=True)
class StageQuizItem:
    index: int
    passage_text: str | None
    prompt: str
    choices: list[str]
    correct_index: int


@dataclass
class ChildStageSession:
    stage: int
    phase: str  # "cards" (Stage0/1만 거침) | "quiz"
    cards: list[Card] = field(default_factory=list)
    card_index: int = 0
    quiz: list[StageQuizItem] = field(default_factory=list)
    quiz_index: int = 0
    correct: int = 0


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (다른 학습 세션과 동일한 설계).
_sessions: dict[str, ChildStageSession] = {}


def start_card_stage(telegram_id: str, stage: int, cards: list[Card], quiz: list[StageQuizItem]) -> None:
    """Stage0(알파벳)/Stage1(파닉스): 카드를 순서대로 보여준 뒤 마지막에 퀴즈."""
    _sessions[telegram_id] = ChildStageSession(stage=stage, phase="cards", cards=cards, quiz=quiz)


def start_quiz_stage(telegram_id: str, stage: int, quiz: list[StageQuizItem]) -> None:
    """Stage2~5: 콘텐츠뱅크 항목을 곧바로 MCQ로 제시."""
    _sessions[telegram_id] = ChildStageSession(stage=stage, phase="quiz", quiz=quiz)


def get_session(telegram_id: str) -> ChildStageSession | None:
    return _sessions.get(telegram_id)


def current_card(telegram_id: str) -> Card | None:
    session = _sessions.get(telegram_id)
    if session is None or session.phase != "cards" or session.card_index >= len(session.cards):
        return None
    return session.cards[session.card_index]


def advance_card(telegram_id: str) -> Card | None:
    """다음 카드를 반환. 카드가 더 없으면 퀴즈 단계로 전환하고 None을 반환한다."""
    session = _sessions[telegram_id]
    session.card_index += 1
    if session.card_index >= len(session.cards):
        session.phase = "quiz"
        return None
    return session.cards[session.card_index]


def current_quiz_item(telegram_id: str) -> StageQuizItem | None:
    session = _sessions.get(telegram_id)
    if session is None or session.phase != "quiz" or session.quiz_index >= len(session.quiz):
        return None
    return session.quiz[session.quiz_index]


@dataclass(frozen=True)
class AnswerResult:
    is_correct: bool
    finished: bool
    next_item: StageQuizItem | None = None
    correct: int = 0
    total: int = 0


def submit_quiz_answer(telegram_id: str, item_index: int, choice_index: int) -> AnswerResult | None:
    session = _sessions.get(telegram_id)
    if session is None or session.phase != "quiz" or session.quiz_index >= len(session.quiz):
        return None

    item = session.quiz[session.quiz_index]
    if item.index != item_index:
        return None  # 이미 지나간 문항에 대한 응답 (stale callback)

    is_correct = choice_index == item.correct_index
    if is_correct:
        session.correct += 1
    session.quiz_index += 1

    if session.quiz_index < len(session.quiz):
        return AnswerResult(is_correct=is_correct, finished=False, next_item=session.quiz[session.quiz_index])

    return AnswerResult(is_correct=is_correct, finished=True, correct=session.correct, total=len(session.quiz))


def finish(telegram_id: str) -> ChildStageSession:
    return _sessions.pop(telegram_id)


# --- Stage6(듣기말하기): 듣기 퀴즈 완료 뒤, 음성메시지 하나를 녹음해 보내면 마무리되는 말하기 연습 ---
# 발음 인식(STT)은 하지 않는다 — 그냥 녹음해서 보내는 행위 자체가 연습이라고 보고 채점 없이 완료 처리한다.

_speaking_practice_waiting: set[str] = set()


def start_speaking_practice(telegram_id: str) -> None:
    _speaking_practice_waiting.add(telegram_id)


def is_awaiting_speaking(telegram_id: str) -> bool:
    return telegram_id in _speaking_practice_waiting


def finish_speaking_practice(telegram_id: str) -> None:
    _speaking_practice_waiting.discard(telegram_id)
