from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    id: str
    kind: str  # "word" | "grammar"
    prompt: str
    choices: list[str]
    correct_index: int


# MVP 기본값: 기획서는 단어 20/문법 10/지문 1을 명시하지만(섹션3-1),
# 콘텐츠 대량 저작은 별도 작업이라 초기 검증용으로 단어 5 + 문법 5 세트로 축소.
# 이후 콘텐츠뱅크(M4)에서 문항 수를 확장한다.
WORD_QUESTIONS: list[Question] = [
    Question("w1", "word", "'apple'의 뜻은?", ["사과", "포도", "바나나", "오렌지"], 0),
    Question("w2", "word", "'run'의 뜻은?", ["달리다", "걷다", "앉다", "서다"], 0),
    Question("w3", "word", "'happy'의 뜻은?", ["행복한", "슬픈", "화난", "피곤한"], 0),
    Question("w4", "word", "'book'의 뜻은?", ["책", "펜", "의자", "창문"], 0),
    Question("w5", "word", "'big'의 반대말은?", ["small", "large", "huge", "tall"], 0),
]

GRAMMAR_QUESTIONS: list[Question] = [
    Question("g1", "grammar", "She ___ to school every day.", ["go", "goes", "going", "went"], 1),
    Question("g2", "grammar", "I ___ a student.", ["am", "is", "are", "be"], 0),
    Question("g3", "grammar", "They ___ playing soccer now.", ["is", "am", "are", "be"], 2),
    Question("g4", "grammar", "He ___ his homework yesterday.", ["do", "does", "did", "doing"], 2),
    Question("g5", "grammar", "There ___ many books on the table.", ["is", "are", "be", "being"], 1),
]

ALL_QUESTIONS: list[Question] = WORD_QUESTIONS + GRAMMAR_QUESTIONS
QUESTIONS_BY_ID: dict[str, Question] = {q.id: q for q in ALL_QUESTIONS}


def determine_level(word_correct: int, word_total: int, grammar_correct: int, grammar_total: int) -> str:
    total_correct = word_correct + grammar_correct
    total_questions = word_total + grammar_total
    ratio = total_correct / total_questions if total_questions else 0.0

    if ratio < 0.4:
        return "beginner"
    if ratio < 0.8:
        return "intermediate"
    return "advanced"
