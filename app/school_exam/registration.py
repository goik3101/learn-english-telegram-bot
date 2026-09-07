from dataclasses import dataclass


@dataclass
class ExamRegistrationSession:
    stage: str = "subject"  # "subject" | "date" | "unit" | "teacher_notes"
    subject: str = ""
    exam_date: str = ""  # ISO 형식(YYYY-MM-DD) 문자열
    unit_info: str = ""


# 소수 사용자 규모(섹션3-2)를 고려해 별도 세션 테이블 없이 프로세스 메모리로 관리 (다른 학습 세션과 동일한 설계).
_sessions: dict[str, ExamRegistrationSession] = {}


def start(telegram_id: str) -> None:
    _sessions[telegram_id] = ExamRegistrationSession()


def is_active(telegram_id: str) -> bool:
    return telegram_id in _sessions


def get_session(telegram_id: str) -> ExamRegistrationSession | None:
    return _sessions.get(telegram_id)


def set_subject(telegram_id: str, subject: str) -> None:
    session = _sessions[telegram_id]
    session.subject = subject
    session.stage = "date"


def set_date(telegram_id: str, exam_date: str) -> None:
    session = _sessions[telegram_id]
    session.exam_date = exam_date
    session.stage = "unit"


def set_unit(telegram_id: str, unit_info: str) -> None:
    session = _sessions[telegram_id]
    session.unit_info = unit_info
    session.stage = "teacher_notes"


def finish(telegram_id: str) -> ExamRegistrationSession:
    return _sessions.pop(telegram_id)
