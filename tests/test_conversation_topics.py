from app.conversation import topics as conversation_topics


def test_pick_today_topic_rotates_through_curriculum_without_use_case():
    seen = {conversation_topics.pick_today_topic(i, None) for i in range(conversation_topics.topic_count())}
    assert seen == set(conversation_topics.CONVERSATION_TOPICS)


def test_pick_today_topic_wraps_around():
    first = conversation_topics.pick_today_topic(0, None)
    wrapped = conversation_topics.pick_today_topic(conversation_topics.topic_count(), None)
    assert first == wrapped


def test_pick_today_topic_prioritizes_matching_target_use_case():
    topic = conversation_topics.pick_today_topic(0, "다음달 유럽 여행을 준비하고 있어요")
    assert topic == "여행"


def test_pick_today_topic_falls_back_to_rotation_when_no_keyword_matches():
    topic = conversation_topics.pick_today_topic(0, "그냥 영어 실력을 키우고 싶어요")
    assert topic == conversation_topics.CONVERSATION_TOPICS[0]
