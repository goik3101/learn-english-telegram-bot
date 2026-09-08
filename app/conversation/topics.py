"""회화 사전 단어학습: 오늘의 대화 주제 선정.

grammar/curriculum.py와 동일하게 코드에 정적 목록으로 둔다. 문법과 달리 주제 자체는
레벨에 무관하게 통용되는 일상 소재라(레벨 차이는 그 주제로 생성되는 단어/대화의 난이도에서만
갈린다) 레벨별로 나누지 않고 하나의 순환 목록을 쓴다.

선정 규칙: 사용자의 target_use_case(자유 입력 텍스트)가 특정 주제 키워드와 겹치면 그 주제를
맨 앞으로 당겨 관심사를 우선 반영하고, 그 뒤로는 conversation_topic_index를 순환시켜
세션마다 다른 주제를 만나게 한다(문법처럼 "완주" 개념이 없어 매 세션 시작 시 인덱스를 그대로
1씩 전진시킨다 — app/handlers/router.py의 _start_conversation_session 참고).
"""

CONVERSATION_TOPICS: list[str] = [
    "자기소개",
    "일상생활",
    "취미와 관심사",
    "여행",
    "음식과 식당",
    "학교생활",
    "쇼핑",
    "날씨와 계절",
    "직장생활",
    "미래 계획",
]

# target_use_case 자유 텍스트를 주제로 매칭하기 위한 느슨한 키워드 목록.
_USE_CASE_KEYWORDS: dict[str, list[str]] = {
    "여행": ["여행", "trip", "travel"],
    "직장생활": ["직장", "업무", "비즈니스", "work", "business", "office"],
    "학교생활": ["학교", "공부", "유학", "study", "school"],
    "쇼핑": ["쇼핑", "shopping"],
    "음식과 식당": ["음식", "요리", "식당", "food", "restaurant"],
}


def topic_count() -> int:
    return len(CONVERSATION_TOPICS)


def _personalized_order(target_use_case: str | None) -> list[str]:
    if not target_use_case:
        return CONVERSATION_TOPICS

    lowered = target_use_case.lower()
    for topic, keywords in _USE_CASE_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return [topic] + [t for t in CONVERSATION_TOPICS if t != topic]
    return CONVERSATION_TOPICS


def pick_today_topic(topic_index: int, target_use_case: str | None = None) -> str:
    order = _personalized_order(target_use_case)
    return order[topic_index % len(order)]
