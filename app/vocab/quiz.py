import random
import re
from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.5


def build_choices(correct_meaning: str, distractors: list[str]) -> tuple[list[str], int]:
    """정답 + 오답 후보를 섞어 (선택지목록, 정답인덱스)를 만든다."""
    choices = [*distractors, correct_meaning]
    random.shuffle(choices)
    return choices, choices.index(correct_meaning)


def _strip_parenthetical(text: str) -> str:
    return re.sub(r"\([^)]*\)", "", text).strip()


def _candidates(correct_meaning: str) -> list[str]:
    """뜻풀이가 '(부가설명) 뜻1, 뜻2'처럼 여러 표현을 담고 있을 때 각각을 비교 대상으로 분리."""
    normalized = _strip_parenthetical(correct_meaning)
    parts = [p.strip() for p in re.split(r"[,/;·]", normalized) if p.strip()]
    return parts or [normalized]


def is_meaning_match(answer: str, correct_meaning: str, threshold: float = MATCH_THRESHOLD) -> bool:
    """주관식 채점: AI 없이 문자열 유사도로 비교 (섹션16 AI 호출 최소화 원칙).

    단어 뜻은 동의어/어미 변형(예: '모호하게 하다' vs '모호하게 만들다')이 흔해서
    단순 부분일치만으로는 정답을 오답 처리하는 경우가 실사용 중 확인됨 — 문자 유사도 기반으로 보완.
    """
    a = answer.strip()
    if not a:
        return False

    candidates = [*_candidates(correct_meaning), _strip_parenthetical(correct_meaning)]
    for candidate in candidates:
        if a == candidate or a in candidate or candidate in a:
            return True
        if SequenceMatcher(None, a, candidate).ratio() >= threshold:
            return True
    return False
