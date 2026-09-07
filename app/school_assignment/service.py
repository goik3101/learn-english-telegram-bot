from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExamQuestion:
    index: int
    question: str
    choices: list[str]
    correct_index: int
    explanation: str | None


@dataclass
class SchoolAssignmentSession:
    level: str
    stage: str = "awaiting_text"  # "select_exam" | "awaiting_text" | "cards" | "exam"
    text: str = ""
    word_count: int = 0
    grammar_explanation: str = ""
    questions: list[ExamQuestion] = field(default_factory=list)
    question_index: int = 0
    correct_count: int = 0
    exam_id: int | None = None  # 학교 시험 관리(M13)에 연결된 시험 — 없으면 단순 학습용 자료
    answers: list[bool] = field(default_factory=list)  # 문항별 정오답, 시험직전복습(M13)의 오답 추출용

    def question_details(self) -> list[dict]:
        return [
            {
                "question": q.question,
                "choices": q.choices,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
                "is_correct": self.answers[i] if i < len(self.answers) else None,
            }
            for i, q in enumerate(self.questions)
        ]


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (다른 학습 세션과 동일한 설계).
_sessions: dict[str, SchoolAssignmentSession] = {}


def start(telegram_id: str, level: str) -> None:
    _sessions[telegram_id] = SchoolAssignmentSession(level=level)


def is_active(telegram_id: str) -> bool:
    return telegram_id in _sessions


def get_session(telegram_id: str) -> SchoolAssignmentSession | None:
    return _sessions.get(telegram_id)


def set_exam_id(telegram_id: str, exam_id: int | None) -> None:
    _sessions[telegram_id].exam_id = exam_id


def enter_cards_stage(telegram_id: str, text: str, word_count: int) -> None:
    session = _sessions[telegram_id]
    session.text = text
    session.word_count = word_count
    session.stage = "cards"


def enter_exam_stage(telegram_id: str, grammar_explanation: str, questions: list[ExamQuestion]) -> None:
    session = _sessions[telegram_id]
    session.grammar_explanation = grammar_explanation
    session.questions = questions
    session.stage = "exam"


def current_question(telegram_id: str) -> ExamQuestion | None:
    session = _sessions.get(telegram_id)
    if session is None or session.question_index >= len(session.questions):
        return None
    return session.questions[session.question_index]


@dataclass(frozen=True)
class AnswerResult:
    is_correct: bool
    finished: bool
    next_question: ExamQuestion | None = None
    correct: int = 0
    total: int = 0


def submit_exam_answer(telegram_id: str, question_index: int, choice_index: int) -> AnswerResult | None:
    session = _sessions.get(telegram_id)
    if session is None or session.stage != "exam" or session.question_index >= len(session.questions):
        return None

    question = session.questions[session.question_index]
    if question.index != question_index:
        return None  # 이미 지나간 문항에 대한 응답 (stale callback)

    is_correct = choice_index == question.correct_index
    session.answers.append(is_correct)
    if is_correct:
        session.correct_count += 1
    session.question_index += 1

    if session.question_index < len(session.questions):
        return AnswerResult(is_correct=is_correct, finished=False, next_question=session.questions[session.question_index])

    return AnswerResult(is_correct=is_correct, finished=True, correct=session.correct_count, total=len(session.questions))


def finish(telegram_id: str) -> SchoolAssignmentSession:
    return _sessions.pop(telegram_id)
