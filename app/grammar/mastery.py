"""문법 파트(part) 숙달 판정 — 순수 함수, AI/DB 호출 없음.

버그리포트: 예전에는 토픽 하나가 통째로 숙달 단위였고, 기준이 "최근 10문제 중 80%"였다.
신규 세트가 하루 5문제로 제한돼 있어 최소 이틀은 지나야 다음 토픽으로 넘어갈 수 있었고,
이게 "5문제만 나가고 다음 단계로 안 넘어가는" 것처럼 느껴지는 원인이었다. 커리큘럼을 훨씬
작은 파트 단위로 쪼개고(app/grammar/curriculum_data.py) 기준도 "최소 5문제 시도 + 최근 5문제
80%"로 낮춰, 하루 세션 하나(5문제)만으로도 파트 하나를 끝낼 수 있게 한다.
"""

MIN_PART_ATTEMPTS = 5
MASTERY_THRESHOLD = 0.8
WEAK_THRESHOLD = 0.5

# V2 학습 엔진: 오답이 이만큼 연속되면(포맷은 그대로 4지선다지만) 다음 문제 전에 개념 재설명 +
# 방금 문제를 정답으로 채운 쉬운 예문을 한 번 더 보여준다(Phase A — 포맷 자체를 빈칸/서술형으로
# 바꾸는 것은 더 큰 작업이라 다음 단계로 남겨둠).
REEXPLAIN_AFTER_CONSECUTIVE_WRONG = 2


def count_consecutive_wrong(recent_results_newest_first: list[bool]) -> int:
    """최신순 정오답 리스트에서 맨 앞(가장 최근)부터 몇 개나 연속으로 틀렸는지 센다."""
    count = 0
    for is_correct in recent_results_newest_first:
        if is_correct:
            break
        count += 1
    return count


def evaluate(recent_results_newest_first: list[bool]) -> str:
    """최신순으로 정렬된 최근 정오답 리스트를 보고 'mastered' | 'weak' | 'in_progress' 중 하나를 반환.

    - 시도 횟수가 MIN_PART_ATTEMPTS 미만이면 아직 판정하지 않는다(in_progress 유지).
    - 최근 MIN_PART_ATTEMPTS개 정답률이 80% 이상이면 mastered(다음 파트로 진행).
    - 50% 미만이면 weak(같은 파트 반복, 취약 오답유형 우선 재출제).
    - 그 사이면 in_progress(더 풀어봐야 판단 가능).
    """
    if len(recent_results_newest_first) < MIN_PART_ATTEMPTS:
        return "in_progress"

    recent = recent_results_newest_first[:MIN_PART_ATTEMPTS]
    accuracy = sum(1 for r in recent if r) / len(recent)

    if accuracy >= MASTERY_THRESHOLD:
        return "mastered"
    if accuracy < WEAK_THRESHOLD:
        return "weak"
    return "in_progress"
