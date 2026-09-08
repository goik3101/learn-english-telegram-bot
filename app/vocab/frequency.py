"""개인 맞춤 난이도 시스템 — 단어 빈도(frequency_rank) 기반 밴드 경계.

Oxford 3000/5000류 실제 사용빈도 순위를 기준으로 한 6단계 밴드. 숫자가 작을수록(밴드 0)
자주 쓰이는 쉬운 단어, 클수록(밴드 5) 드물고 어려운 단어.
"""

WORD_FREQUENCY_BANDS: list[tuple[int, int]] = [
    (1, 1000),
    (1001, 2000),
    (2001, 3000),
    (3001, 5000),
    (5001, 8000),
    (8001, 999_999),
]

MAX_WORD_BAND = len(WORD_FREQUENCY_BANDS) - 1


def band_range(band: int) -> tuple[int, int]:
    band = max(0, min(band, MAX_WORD_BAND))
    return WORD_FREQUENCY_BANDS[band]
