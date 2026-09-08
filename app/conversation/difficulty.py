"""개인 맞춤 난이도 시스템(회화): CEFR형 6단계 conversation_level.

전체 placement_level(beginner/intermediate/advanced)과는 별개로, 회화 세션 종료 시 사용자가
직접 매기는 "쉬웠어요/적당해요/어려웠어요" 피드백만으로 오르내리는 독립적인 축이다.
"""

import re

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
MIN_LEVEL = 0
MAX_LEVEL = len(CEFR_LEVELS) - 1
DEFAULT_LEVEL = 2  # B1 — 무난한 시작점

# 레벨별로 "이 순위보다 훨씬 흔한 단어여야 한다"는 대략적 상한선. words.frequency_rank와 비교해
# AI 응답이 사용자 수준보다 명확히 어려운 단어를 쓰고 있는지 가늠하는 용도(엄밀한 사전은 아님).
_LEVEL_MAX_RANK = [500, 1200, 2500, 4000, 7000, 999_999]

# 활용형(-ing/-ed/-ly 등)이 원형과 다른 단어로 오판되지 않도록 시도해볼 접미사 후보들.
_SUFFIXES = ["edly", "ing", "ies", "ed", "es", "ly", "er", "est", "s"]

TOO_HARD_MIN_MATCHES = 2  # 이 개수 이상 "명확히 어려운 단어"가 매칭되면 재생성을 요청한다.


def level_name(level: int) -> str:
    level = max(MIN_LEVEL, min(level, MAX_LEVEL))
    return CEFR_LEVELS[level]


def max_rank_for_level(level: int) -> int:
    level = max(MIN_LEVEL, min(level, MAX_LEVEL))
    return _LEVEL_MAX_RANK[level]


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z']+", text)]


def candidate_forms(word: str) -> list[str]:
    """원형 후보 목록(자기 자신 + 접미사를 뗀 버전) — frequency_rank 조회 시 순서대로 시도."""
    forms = [word]
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            forms.append(word[: -len(suffix)])
    return forms


def is_too_difficult(text: str, level: int, rank_by_word: dict[str, int]) -> bool:
    """rank_by_word: candidate_forms로 만든 원형 후보들을 키로 하는 frequency_rank 조회 결과.

    문자열 단순 대조(예: 학습자의 known/unknown 단어 목록과 정확히 일치하는지)가 아니라,
    실제 사용빈도 구간(frequency_rank)이 사용자 레벨의 상한선을 명확히 넘는지로 판단한다.
    """
    threshold = max_rank_for_level(level)
    hard_count = 0
    for token in tokenize(text):
        for form in candidate_forms(token):
            rank = rank_by_word.get(form)
            if rank is not None:
                if rank > threshold:
                    hard_count += 1
                break  # 첫 매칭 후보로만 판단(중복 카운트 방지)
    return hard_count >= TOO_HARD_MIN_MATCHES


def adjust_level(current_level: int, feedback: str) -> int:
    if feedback == "easy":
        return min(current_level + 1, MAX_LEVEL)
    if feedback == "hard":
        return max(current_level - 1, MIN_LEVEL)
    return current_level
