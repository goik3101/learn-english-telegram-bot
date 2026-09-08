"""M15 Stage0(알파벳)/Stage1(파닉스) 고정 커리큘럼.

26개 알파벳과 대표적인 파닉스 단어가족은 개수가 한정되어 있고 매번 달라질 필요가 없어,
placement/questions.py(레벨진단 문항)와 동일한 방식으로 AI 생성 없이 코드에 정적으로 둔다.
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class LetterCard:
    letter: str
    example_word: str
    meaning_ko: str
    emoji: str


ALPHABET: list[LetterCard] = [
    LetterCard("A", "Apple", "사과", "🍎"),
    LetterCard("B", "Ball", "공", "⚽"),
    LetterCard("C", "Cat", "고양이", "🐱"),
    LetterCard("D", "Dog", "강아지", "🐶"),
    LetterCard("E", "Egg", "달걀", "🥚"),
    LetterCard("F", "Fish", "물고기", "🐟"),
    LetterCard("G", "Grape", "포도", "🍇"),
    LetterCard("H", "Hat", "모자", "🎩"),
    LetterCard("I", "Ice cream", "아이스크림", "🍦"),
    LetterCard("J", "Juice", "주스", "🧃"),
    LetterCard("K", "Kite", "연", "🪁"),
    LetterCard("L", "Lion", "사자", "🦁"),
    LetterCard("M", "Monkey", "원숭이", "🐒"),
    LetterCard("N", "Nest", "둥지", "🪺"),
    LetterCard("O", "Orange", "오렌지", "🍊"),
    LetterCard("P", "Panda", "판다", "🐼"),
    LetterCard("Q", "Queen", "여왕", "👑"),
    LetterCard("R", "Rabbit", "토끼", "🐰"),
    LetterCard("S", "Sun", "해", "☀️"),
    LetterCard("T", "Tiger", "호랑이", "🐯"),
    LetterCard("U", "Umbrella", "우산", "☂️"),
    LetterCard("V", "Violin", "바이올린", "🎻"),
    LetterCard("W", "Watermelon", "수박", "🍉"),
    LetterCard("X", "Fox", "여우", "🦊"),
    LetterCard("Y", "Yo-yo", "요요", "🪀"),
    LetterCard("Z", "Zebra", "얼룩말", "🦓"),
]


@dataclass(frozen=True)
class PhonicsCard:
    pattern: str
    example_words: list[str]
    meaning_ko: str


PHONICS: list[PhonicsCard] = [
    PhonicsCard("-at", ["cat", "hat", "bat", "mat"], "끝소리가 '앳'으로 나는 단어 가족이에요"),
    PhonicsCard("-an", ["can", "fan", "man", "pan"], "끝소리가 '앤'으로 나는 단어 가족이에요"),
    PhonicsCard("-ig", ["big", "pig", "wig", "dig"], "끝소리가 '이그'로 나는 단어 가족이에요"),
    PhonicsCard("-og", ["dog", "log", "fog", "jog"], "끝소리가 '오그'로 나는 단어 가족이에요"),
    PhonicsCard("-ug", ["bug", "hug", "mug", "rug"], "끝소리가 '어그'로 나는 단어 가족이에요"),
    PhonicsCard("-et", ["pet", "net", "jet", "wet"], "끝소리가 '엣'으로 나는 단어 가족이에요"),
    PhonicsCard("-ot", ["hot", "pot", "dot", "not"], "끝소리가 '앗'으로 나는 단어 가족이에요"),
    PhonicsCard("-ip", ["lip", "sip", "tip", "zip"], "끝소리가 '입'으로 나는 단어 가족이에요"),
]


@dataclass(frozen=True)
class QuizQuestion:
    index: int
    prompt: str
    choices: list[str]
    correct_index: int


def build_alphabet_quiz(count: int = 5) -> list[QuizQuestion]:
    sample = random.sample(ALPHABET, min(count, len(ALPHABET)))
    others = [c for c in ALPHABET]
    questions = []
    for i, card in enumerate(sample):
        distractor_pool = [c.example_word for c in others if c.letter != card.letter]
        distractors = random.sample(distractor_pool, 3)
        choices = distractors + [card.example_word]
        random.shuffle(choices)
        questions.append(
            QuizQuestion(
                index=i,
                prompt=f"알파벳 '{card.letter}'로 시작하는 단어는 무엇일까요?",
                choices=choices,
                correct_index=choices.index(card.example_word),
            )
        )
    return questions


def build_phonics_quiz(count: int = 5) -> list[QuizQuestion]:
    sample = random.sample(PHONICS, min(count, len(PHONICS)))
    questions = []
    for i, card in enumerate(sample):
        correct_word = random.choice(card.example_words)
        other_families = [c for c in PHONICS if c.pattern != card.pattern]
        distractor_families = random.sample(other_families, 3)
        distractors = [random.choice(c.example_words) for c in distractor_families]
        choices = distractors + [correct_word]
        random.shuffle(choices)
        questions.append(
            QuizQuestion(
                index=i,
                prompt=f"다음 중 '{card.pattern}' 가족에 속하는 단어는 무엇일까요?",
                choices=choices,
                correct_index=choices.index(correct_word),
            )
        )
    return questions
