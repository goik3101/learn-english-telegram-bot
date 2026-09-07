from dataclasses import dataclass

from app.school_assignment.service import ExamQuestion


@dataclass
class ExamReviewSession:
    exam_id: int
    questions: list[ExamQuestion]
    index: int = 0
    correct: int = 0


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (다른 학습 세션과 동일한 설계).
_sessions: dict[str, ExamReviewSession] = {}


def start(telegram_id: str, exam_id: int, questions: list[ExamQuestion]) -> None:
    _sessions[telegram_id] = ExamReviewSession(exam_id=exam_id, questions=questions)


def is_active(telegram_id: str) -> bool:
    return telegram_id in _sessions


def get_session(telegram_id: str) -> ExamReviewSession | None:
    return _sessions.get(telegram_id)


def current_question(telegram_id: str) -> ExamQuestion | None:
    session = _sessions.get(telegram_id)
    if session is None or session.index >= len(session.questions):
        return None
    return session.questions[session.index]


@dataclass(frozen=True)
class AnswerResult:
    is_correct: bool
    finished: bool
    next_question: ExamQuestion | None = None
    correct: int = 0
    total: int = 0


def submit_answer(telegram_id: str, question_index: int, choice_index: int) -> AnswerResult | None:
    session = _sessions.get(telegram_id)
    if session is None or session.index >= len(session.questions):
        return None

    question = session.questions[session.index]
    if question.index != question_index:
        return None  # 이미 지나간 문항에 대한 응답 (stale callback)

    is_correct = choice_index == question.correct_index
    if is_correct:
        session.correct += 1
    session.index += 1

    if session.index < len(session.questions):
        return AnswerResult(is_correct=is_correct, finished=False, next_question=session.questions[session.index])

    return AnswerResult(is_correct=is_correct, finished=True, correct=session.correct, total=len(session.questions))


def finish(telegram_id: str) -> ExamReviewSession:
    return _sessions.pop(telegram_id)
