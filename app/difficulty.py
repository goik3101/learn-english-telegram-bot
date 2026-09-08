"""개인 맞춤 난이도 시스템 — 단어/문법/독해가 공유하는 적응형 밴드 조정 로직 (순수 함수, AI 호출 없음).

최근 N개(기본 10개) 성취도를 보고 80% 이상이면 한 단계 올리고, 50% 미만이면 한 단계 내리고,
그 사이는 유지한다. 최소 학습량(N개)을 채우기 전에는 조정하지 않아 문제 몇 개만에 난이도가
왔다갔다 하는 것을 방지한다(사용자 요청 반영).
"""

MIN_SAMPLE_SIZE = 10
ADVANCE_THRESHOLD = 0.8
REGRESS_THRESHOLD = 0.5


def next_band(current_band: int, recent_results_newest_first: list[bool], min_band: int = 0, max_band: int | None = None) -> int:
    """recent_results_newest_first: 최신 순으로 정렬된 정오답 리스트."""
    if len(recent_results_newest_first) < MIN_SAMPLE_SIZE:
        return current_band

    recent = recent_results_newest_first[:MIN_SAMPLE_SIZE]
    accuracy = sum(1 for r in recent if r) / len(recent)

    if accuracy >= ADVANCE_THRESHOLD:
        new_band = current_band + 1
    elif accuracy < REGRESS_THRESHOLD:
        new_band = current_band - 1
    else:
        return current_band

    new_band = max(new_band, min_band)
    if max_band is not None:
        new_band = min(new_band, max_band)
    return new_band
