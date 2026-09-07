from dataclasses import dataclass, field

from app.placement.questions import ALL_QUESTIONS, QUESTIONS_BY_ID, Question, determine_level


@dataclass
class PlacementSession:
    index: int = 0
    word_correct: int = 0
    word_total: int = 0
    grammar_correct: int = 0
    grammar_total: int = 0
    answered_ids: set[str] = field(default_factory=set)


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리.
# 서버 재시작 시 진행 중이던 진단은 초기화되며, 사용자는 /레벨진단으로 다시 시작하면 된다.
_sessions: dict[str, PlacementSession] = {}


def start_session(telegram_id: str) -> Question:
    _sessions[telegram_id] = PlacementSession()
    return ALL_QUESTIONS[0]


def has_active_session(telegram_id: str) -> bool:
    return telegram_id in _sessions


def get_question(question_id: str) -> Question | None:
    return QUESTIONS_BY_ID.get(question_id)


@dataclass
class AnswerResult:
    finished: bool
    next_question: Question | None = None
    word_correct: int = 0
    word_total: int = 0
    grammar_correct: int = 0
    grammar_total: int = 0
    level: str | None = None


def submit_answer(telegram_id: str, question_id: str, choice_index: int) -> AnswerResult | None:
    session = _sessions.get(telegram_id)
    question = QUESTIONS_BY_ID.get(question_id)
    if session is None or question is None or question_id in session.answered_ids:
        return None

    session.answered_ids.add(question_id)
    is_correct = choice_index == question.correct_index

    if question.kind == "word":
        session.word_total += 1
        if is_correct:
            session.word_correct += 1
    else:
        session.grammar_total += 1
        if is_correct:
            session.grammar_correct += 1

    session.index += 1

    if session.index < len(ALL_QUESTIONS):
        return AnswerResult(finished=False, next_question=ALL_QUESTIONS[session.index])

    level = determine_level(session.word_correct, session.word_total, session.grammar_correct, session.grammar_total)
    result = AnswerResult(
        finished=True,
        word_correct=session.word_correct,
        word_total=session.word_total,
        grammar_correct=session.grammar_correct,
        grammar_total=session.grammar_total,
        level=level,
    )
    del _sessions[telegram_id]
    return result
