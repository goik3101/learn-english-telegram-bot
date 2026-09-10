"""오늘의 주제 기반 통합 학습: 단어/해석(Reading)/회화가 서로 무관하게 각자 어휘를 뽑다 보니
해석 지문이 사용자 수준과 동떨어진 학술 어휘로 생성되는 문제(사용자 피드백)를 막기 위해, 하루
단위로 "오늘의 주제"를 하나 정해서 세 영역이 그 주제의 핵심 단어 풀을 공유하게 한다.

M19(회화 사전 단어학습)에서는 회화 전용으로 이 로직이 있었지만, 이제 단어학습/해석/회화가 전부
공유하므로 여기(app/topics.py)로 일반화했다 — app/conversation/topics.py는 폐기.

주제는 전부 일상적이고 구체적인 소재로만 구성한다(추상적·학술적 주제는 사용자 레벨이 충분히
올라가기 전까지 다루지 않음 — 해석 지문이 "algorithmic accountability" 같은 학술 어휘로 새던
원인이 바로 이런 주제 부재였음).
"""

import random

DAILY_TOPICS: list[str] = [
    "자기소개",
    "일상생활",
    "취미와 관심사",
    "여행",
    "음식과 식당",
    "학교생활",
    "쇼핑",
    "날씨와 계절",
    "가족",
    "건강",
]

# 최근 이만큼의 날짜 안에 이미 쓴 주제는 오늘 다시 고르지 않는다(사용자 요청: "너무 자주 반복되지
# 않게"). 주제 수(10개)보다 크게 잡으면 평소엔 거의 안 겹치되, 데이터가 부족한 초반에는 자연히
# 전체 주제를 한 바퀴 돈 뒤에야 반복되기 시작한다.
AVOID_RECENT_DAYS = 5

# target_use_case 자유 텍스트를 주제로 매칭하기 위한 느슨한 키워드 목록.
_USE_CASE_KEYWORDS: dict[str, list[str]] = {
    "여행": ["여행", "trip", "travel"],
    "학교생활": ["학교", "공부", "유학", "study", "school"],
    "쇼핑": ["쇼핑", "shopping"],
    "음식과 식당": ["음식", "요리", "식당", "food", "restaurant"],
    "건강": ["건강", "운동", "다이어트", "health", "fitness", "exercise"],
    "가족": ["가족", "family"],
}


def pick_topic(target_use_case: str | None, recent_topics: list[str]) -> str:
    """recent_topics: 최근 AVOID_RECENT_DAYS일 안에 이미 사용한 주제 목록(오늘 제외) — 이번 선정에서
    제외한다. 전부 최근에 나왔다면(예: 주제 수보다 관찰 기간이 길게 잡힌 경우) 제약 없이 전체에서
    고른다(fail-open).
    """
    candidates = [t for t in DAILY_TOPICS if t not in recent_topics] or DAILY_TOPICS

    if target_use_case:
        lowered = target_use_case.lower()
        for topic, keywords in _USE_CASE_KEYWORDS.items():
            if topic in candidates and any(keyword.lower() in lowered for keyword in keywords):
                return topic

    return random.choice(candidates)
