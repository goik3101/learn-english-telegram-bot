from dataclasses import dataclass

# 섹션14: 간격 반복(SRS) 계산 로직 — AI 호출 없이 서버 코드로 처리
INITIAL_INTERVAL_DAYS = 1
INITIAL_EASE = 1.7  # 암기 취약 보정 (기획서: 일반은 2.0, 이 서비스는 1.7로 시작)
MIN_EASE = 1.3

DEFAULT_DAILY_NEW_WORDS = 5
MIN_DAILY_NEW_WORDS = 3
MAX_DAILY_NEW_WORDS = 15


@dataclass(frozen=True)
class SrsResult:
    interval_days: int
    ease: float


def apply_correct(interval_days: int, ease: float) -> SrsResult:
    new_interval = max(1, round(interval_days * ease))
    return SrsResult(interval_days=new_interval, ease=ease)


def apply_incorrect(interval_days: int, ease: float) -> SrsResult:
    new_ease = max(MIN_EASE, round(ease - 0.2, 2))
    return SrsResult(interval_days=INITIAL_INTERVAL_DAYS, ease=new_ease)


def adjust_daily_new_word_limit(current_limit: int, accuracy: float) -> int:
    """정답률이 좋아지면 자동 증가, 나빠지면 자동 감소 (섹션3-1/18 [결정필요]: 기준은 임의로 정함 — 90%/50%)."""
    if accuracy >= 0.9:
        return min(MAX_DAILY_NEW_WORDS, current_limit + 1)
    if accuracy < 0.5:
        return max(MIN_DAILY_NEW_WORDS, current_limit - 1)
    return current_limit
