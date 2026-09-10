from app import topics


def test_pick_topic_returns_daily_topic_when_no_constraints():
    topic = topics.pick_topic(None, [])
    assert topic in topics.DAILY_TOPICS


def test_pick_topic_avoids_recent_topics():
    recent = topics.DAILY_TOPICS[:-1]  # 마지막 하나만 남기고 전부 "최근에 썼다"고 가정
    for _ in range(20):
        assert topics.pick_topic(None, recent) == topics.DAILY_TOPICS[-1]


def test_pick_topic_falls_back_to_full_list_when_all_recent():
    # 관찰 기간이 주제 수보다 길게 잡혀 전부 "최근"으로 잡혀도 크래시 없이 하나를 골라야 한다.
    topic = topics.pick_topic(None, list(topics.DAILY_TOPICS))
    assert topic in topics.DAILY_TOPICS


def test_pick_topic_prioritizes_matching_target_use_case():
    topic = topics.pick_topic("다음달 유럽 여행을 준비하고 있어요", [])
    assert topic == "여행"


def test_pick_topic_use_case_match_still_respects_recent_exclusion():
    topic = topics.pick_topic("다음달 유럽 여행을 준비하고 있어요", ["여행"])
    assert topic != "여행"
