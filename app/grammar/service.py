from dataclasses import dataclass


@dataclass(frozen=True)
class GrammarQuestion:
    question_id: int
    topic: str | None
    concept_intro: str | None
    prompt: str
    choices: list[str]
    correct_index: int
    explanation: str | None
    part_id: int | None = None
    error_type: str | None = None
    part_name: str | None = None


@dataclass
class GrammarSession:
    items: list[GrammarQuestion]
    is_review: bool
    index: int = 0
    correct: int = 0


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (레벨진단/단어학습과 동일한 설계 결정).
_sessions: dict[str, GrammarSession] = {}


def start_session(telegram_id: str, items: list[GrammarQuestion], is_review: bool) -> GrammarQuestion | None:
    _sessions[telegram_id] = GrammarSession(items=items, is_review=is_review)
    return items[0] if items else None


def is_active(telegram_id: str) -> bool:
    return telegram_id in _sessions


def abandon_session(telegram_id: str) -> None:
    """/학습중단: 지금까지 답한 문항은 이미 채점/저장됐으므로(submit_answer가 매번 즉시 기록),
    남은 미답변 문항만 버리고 세션을 지운다."""
    _sessions.pop(telegram_id, None)


@dataclass(frozen=True)
class AnswerResult:
    is_correct: bool
    question: GrammarQuestion
    finished: bool
    next_question: GrammarQuestion | None = None
    correct: int = 0
    total: int = 0
    is_review: bool = False


def submit_answer(telegram_id: str, question_id: int, choice_index: int) -> AnswerResult | None:
    session = _sessions.get(telegram_id)
    if session is None or session.index >= len(session.items):
        return None

    item = session.items[session.index]
    if item.question_id != question_id:
        return None  # 이미 지나간 문항에 대한 응답 (stale callback)

    is_correct = choice_index == item.correct_index
    if is_correct:
        session.correct += 1
    session.index += 1

    if session.index < len(session.items):
        return AnswerResult(
            is_correct=is_correct,
            question=item,
            finished=False,
            next_question=session.items[session.index],
            is_review=session.is_review,
        )

    total = len(session.items)
    correct = session.correct
    is_review = session.is_review
    del _sessions[telegram_id]
    return AnswerResult(
        is_correct=is_correct,
        question=item,
        finished=True,
        correct=correct,
        total=total,
        is_review=is_review,
    )
