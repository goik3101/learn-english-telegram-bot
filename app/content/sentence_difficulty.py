"""V2 학습 엔진: 문장 난이도를 단어 난이도와 독립적으로 검사하는 하드 제약(코드 레벨, AI 자율 아님).

AI에게 "쉬운 문장을 써라"라고 프롬프트로만 지시하는 것은 강제력이 없다(무시해도 코드가 못
잡아낸다) — 그래서 생성된 텍스트를 여기서 실제로 검사하고, 기준을 넘으면 호출부가 재생성하도록
`generate -> validate -> reject -> regenerate` 구조를 만든다.

이번 구현(설계 문서 "B-1 단계") 범위는 문장 길이 + 목표 단어 목록 밖(미지) 단어 비율 검사다.
절 개수/수동태/관계대명사/분사/시제 정밀 탐지("B-2 단계")는 더 큰 작업이라 다음 단계로 남겨둔다.
"""

import re
from dataclasses import dataclass

# 목표 단어 목록에는 절대 안 들어가지만 기초 학습자도 이미 아는 흔한 기본어휘(관사/전치사 등
# 문법 기능어 + 요일/시간/빈도부사/기초형용사 등) — 이런 단어까지 "미지단어"로 세면 정상적인
# 문장도 대부분 걸린다. 활용형(went/trips 등)까지 정확히 매칭하긴 어려우니 어간 앞부분 일치까지
# 허용하는 느슨한 기준을 쓴다.
STOPWORDS = {
    "a", "an", "the", "is", "am", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "at", "and", "or", "but", "so", "if", "as", "than",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "this", "that", "these", "those", "with", "for", "from", "by", "about", "into",
    "my", "your", "his", "its", "our", "their", "not", "no", "do", "does", "did",
    "have", "has", "had", "will", "would", "can", "could", "should", "may", "might",
    "very", "just", "then", "there", "here", "when", "what", "who", "how", "because",
    "day", "days", "today", "every", "like", "people", "time", "way", "get", "got",
    "go", "goes", "went", "one", "good", "new", "old", "big", "small", "many",
    "much", "also", "too", "again", "always", "never", "often", "sometimes",
    "after", "before", "during", "while", "until", "since", "over", "under",
    "between", "around", "through", "up", "down", "out", "off", "only", "more",
    "most", "some", "any", "all", "each", "other", "such", "own", "school",
    "home", "friend", "friends", "family", "week", "morning", "night",
}


def unknown_word_ratio(text: str, allowed_words: list[str]) -> float:
    """텍스트에서 목표 단어 목록(+기능어) 밖의 단어가 차지하는 비율을 대략 계산한다."""
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    content_tokens = [t for t in tokens if t not in STOPWORDS]
    if not content_tokens:
        return 0.0
    allowed_stems = {w.lower()[:4] for w in allowed_words if len(w) >= 4} | {
        w.lower() for w in allowed_words
    }
    unknown = [t for t in content_tokens if t not in allowed_stems and t[:4] not in allowed_stems]
    return len(unknown) / len(content_tokens)


def longest_sentence_word_count(text: str) -> int:
    """가장 긴 문장의 단어 수(공백 기준) — 문장 하나에 몰아넣은 긴 글을 잡아내기 위함."""
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    if not sentences:
        return 0
    return max(len(re.findall(r"[a-zA-Z']+", s)) for s in sentences)


@dataclass(frozen=True)
class SentenceDifficultyLimits:
    max_words_per_sentence: int
    max_unknown_word_ratio: float = 0.3


# 레벨이 오를수록 문장이 길어지는 것은 자연스럽지만, 그 상한도 AI 자율이 아니라 코드가 정한다
# (요청사항 5: "조금 어려운 문제"를 주는 방향으로 설계하지 않는다 — 기본값은 쉬운 고교 기본 영어).
LIMITS_BY_LEVEL: dict[str, SentenceDifficultyLimits] = {
    "beginner": SentenceDifficultyLimits(max_words_per_sentence=12),
    "intermediate": SentenceDifficultyLimits(max_words_per_sentence=16),
    "advanced": SentenceDifficultyLimits(max_words_per_sentence=22),
}


def limits_for_level(level: str) -> SentenceDifficultyLimits:
    return LIMITS_BY_LEVEL.get(level, LIMITS_BY_LEVEL["beginner"])


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    violations: list[str]


def validate(text: str, allowed_words: list[str], limits: SentenceDifficultyLimits) -> ValidationResult:
    violations: list[str] = []

    longest = longest_sentence_word_count(text)
    if longest > limits.max_words_per_sentence:
        violations.append(f"문장이 너무 깁니다 ({longest}단어 > 최대 {limits.max_words_per_sentence}단어)")

    ratio = unknown_word_ratio(text, allowed_words)
    if ratio > limits.max_unknown_word_ratio:
        violations.append(
            f"목표 단어 목록 밖 단어 비율이 높습니다 ({ratio:.0%} > {limits.max_unknown_word_ratio:.0%})"
        )

    return ValidationResult(passed=not violations, violations=violations)
