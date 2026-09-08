from app.telegram_client import build_reply_keyboard

TODAY_LEARNING = "🗓 오늘의 학습"
VOCAB_STUDY = "📚 단어 학습"
VOCAB_QUIZ = "🔤 단어 시험"
GRAMMAR_STUDY = "✍️ 문법 학습"
READING = "📖 해석(Reading)"
CONVERSATION = "💬 회화(Conversation)"
TEXT_PASTE = "📄 텍스트 붙여넣기 학습"
SCHOOL_ASSIGNMENT = "📝 학교 수행평가"
SCHOOL_EXAM = "📅 시험관리"
REVIEW = "🔁 복습"
PROGRESS = "📊 진도 확인"
ADMIN = "⚙️ 관리자"

# 아직 구현되지 않은 버튼 (섹션19-7: 미구현 항목도 UI에는 노출하되 안내 메시지로 대체) — 현재는 없음, 모두 구현됨
NOT_YET_IMPLEMENTED: dict[str, str] = {}


def build_main_menu_keyboard(is_admin: bool) -> dict:
    rows = [
        [TODAY_LEARNING, VOCAB_STUDY],
        [VOCAB_QUIZ, GRAMMAR_STUDY],
        [READING, CONVERSATION],
        [TEXT_PASTE, SCHOOL_ASSIGNMENT],
        [SCHOOL_EXAM],
        [REVIEW, PROGRESS],
    ]
    if is_admin:
        rows.append([ADMIN])
    return build_reply_keyboard(rows)


# 텔레그램 '/' 자동완성 메뉴 등록용 영문 명령어 (한글 명령어는 텔레그램 규칙상 등록 불가 — 타이핑으로는 계속 동작함).
# (영문명령어, 설명, 라우터에서 매칭할 한글 명령어들) — 라우터는 이 목록으로 영문 별칭도 함께 인식한다.
GENERAL_COMMANDS: list[tuple[str, str]] = [
    ("start", "시작하기 / 승인요청"),
    ("menu", "메인 메뉴 보기"),
    ("todaylearning", "오늘의 학습 (단어→문법 자동 진행)"),
    ("leveltest", "레벨 진단 다시 응시"),
    ("vocabstudy", "단어 학습 (아는단어/모르는단어)"),
    ("vocabquiz", "단어 시험 (반복 가능)"),
    ("grammarstudy", "문법 학습 (하루 1회)"),
    ("review", "문법 복습 (무제한)"),
    ("reading", "해석(Reading) — 지문 해석 후 AI 힌트/피드백"),
    ("conversation", "회화(Conversation) — AI와 5턴 영어 대화 (하루 1회)"),
    ("progress", "진도 확인 — 레벨/단어/문법/해석/회화 학습 현황"),
    ("customtext", "텍스트 붙여넣기 학습 — 원하는 글을 붙여넣고 단어/해석 학습"),
    ("schooltask", "학교 수행평가 — 지문 붙여넣기 → 단어학습 → 문법해설 → 예상시험문제"),
    ("examregister", "학교 시험 등록 — 과목/날짜/단원/선생님강조사항"),
    ("examlist", "등록된 학교 시험 목록 (D-Day)"),
    ("examreview", "시험직전복습 — 연결된 자료의 오답만 다시 풀기"),
]

ADMIN_ONLY_COMMANDS: list[tuple[str, str]] = [
    ("pending", "승인 대기 사용자 목록"),
    ("approve", "사용자 승인 (예: /approve 123456)"),
    ("users", "전체 사용자 목록 (아이디/나이/모드/오늘활동)"),
    ("aiusage", "AI 사용량 — Gemini/TTS 오늘·이번달 호출 수"),
]
