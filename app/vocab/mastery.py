"""V2 학습 엔진: 단어 암기(vocabulary memory) 학습단계 상태머신 — 순수 함수, DB/AI 호출 없음
(app/grammar/mastery.py와 같은 스타일).

"한 번 맞춤 = 암기 완료"로 처리하지 않기 위해, 신규 단어가 SRS ease 기반 정규 간격 성장에
들어가기 전에 최소 1번의 재확인(학습단계, learning step)을 강제한다:

new/learning_step_1 --(정답)--> learning_step_2 --(정답, 보통 다음날)--> review --(정답 반복)--> mastered

오답이면 어느 단계에서든 learning_step_1로 되돌아가고 연속정답 스트릭이 0으로 리셋된다 — 완전히
처음(new)으로 되돌리지는 않는다(이미 한 번은 노출됐다는 사실 자체는 유효한 신호이므로).
"""

from dataclasses import dataclass

MASTERY_NEW = "new"
MASTERY_STEP_1 = "learning_step_1"
MASTERY_STEP_2 = "learning_step_2"
MASTERY_REVIEW = "review"
MASTERY_MASTERED = "mastered"

# review 단계에서 연속 이만큼 더 맞아야 mastered로 승격 — "정답 한 번"이 아니라 최소 반복
# 기준을 두어(app/difficulty.py의 "최소 학습량 채우기 전엔 판정 안 함" 철학과 동일) 우연한
# 정답 한 번으로 곧장 mastered 처리되지 않게 한다.
MASTERED_STREAK = 3

LEARNING_STEP_INTERVAL_DAYS = 1


@dataclass(frozen=True)
class MasteryTransition:
    mastery: str
    consecutive_correct: int
    is_learning_step: bool  # True면 호출부가 ease 기반 간격 성장 대신 짧은 고정 간격을 써야 한다


def apply_answer(current_mastery: str, consecutive_correct: int, is_correct: bool) -> MasteryTransition:
    if not is_correct:
        return MasteryTransition(MASTERY_STEP_1, 0, is_learning_step=True)

    new_streak = consecutive_correct + 1

    if current_mastery in (MASTERY_NEW, MASTERY_STEP_1):
        # 첫 정답 — 아직 "암기했다"고 보지 않는다. 짧은 간격으로 재확인만 예약한다.
        return MasteryTransition(MASTERY_STEP_2, new_streak, is_learning_step=True)

    if current_mastery == MASTERY_STEP_2:
        # 학습단계 재확인까지 통과 — 이제부터 정규 SRS 간격 성장을 시작한다.
        return MasteryTransition(MASTERY_REVIEW, new_streak, is_learning_step=False)

    # review 또는 mastered: 정규 SRS 성장 계속, 스트릭이 충분하면 mastered로 승격.
    mastery = MASTERY_MASTERED if new_streak >= MASTERED_STREAK else MASTERY_REVIEW
    return MasteryTransition(mastery, new_streak, is_learning_step=False)
