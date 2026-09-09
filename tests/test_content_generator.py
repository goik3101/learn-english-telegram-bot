import asyncio
import json

from app.content import generator


def run(coro):
    return asyncio.run(coro)


def test_generate_words_parses_and_filters_malformed(monkeypatch):
    valid = {
        "word": "apple",
        "meaning_ko": "사과",
        "part_of_speech": "noun",
        "pronunciation": "/ˈæpəl/",
        "mnemonic": "이 단어를 이렇게 기억해보세요: 사과는 하루에 하나씩(an apple a day).",
        "example_sentences": [
            {"sentence": "I ate an apple.", "translation": "나는 사과를 먹었다."},
            {"sentence": "She bought a red apple.", "translation": "그녀는 빨간 사과를 샀다."},
        ],
        "frequency_rank": 850,
    }
    malformed = {"word": "broken"}  # 필수 필드 누락

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        assert "beginner" in prompt
        return json.dumps([valid, malformed])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_words("beginner", 2))
    expected = {**valid, "example_sentence": "I ate an apple.", "example_translation": "나는 사과를 먹었다."}
    assert result == [expected]


def test_generate_grammar_questions_parses_and_filters_malformed(monkeypatch):
    valid = {
        "topic": "현재완료",
        "concept_intro": "현재완료는 과거에 시작된 일이 현재까지 이어질 때 쓴다.",
        "prompt": "She ___ lived here for 10 years.",
        "choices": ["live", "lived", "has lived", "living"],
        "correct_index": 2,
        "explanation": "현재완료 계속 용법",
    }
    bad_choice_count = {**valid, "choices": ["a", "b"]}
    bad_index = {**valid, "correct_index": 9}
    missing_concept_intro = {k: v for k, v in valid.items() if k != "concept_intro"}

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        assert "advanced" in prompt
        return json.dumps([valid, bad_choice_count, bad_index, missing_concept_intro])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_grammar_questions("advanced", 4))
    assert result == [{**valid, "key_vocabulary": []}]


def test_generate_grammar_questions_keeps_valid_key_vocabulary_and_drops_malformed_entries(monkeypatch):
    good_vocab = {
        "word": "sustainable",
        "meaning_ko": "지속 가능한",
        "part_of_speech": "adjective",
        "pronunciation": "/səˈsteɪnəbl/",
        "example_sentence": "We need a sustainable plan.",
        "example_translation": "우리는 지속 가능한 계획이 필요하다.",
    }
    bad_vocab = {"word": "onlyword"}  # 필수 필드 누락
    question = {
        "topic": "가정법",
        "concept_intro": "가정법은 실제와 반대되는 상황을 가정할 때 쓴다.",
        "prompt": "If I ___ rich, I would travel.",
        "choices": ["am", "were", "was", "be"],
        "correct_index": 1,
        "explanation": "가정법 과거는 were를 쓴다.",
        "key_vocabulary": [good_vocab, bad_vocab],
    }

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps([question])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_grammar_questions("intermediate", 1))
    assert len(result) == 1
    assert result[0]["key_vocabulary"] == [good_vocab]


def test_generate_topic_words_parses_and_filters_malformed(monkeypatch):
    valid = {
        "word": "suitcase",
        "meaning_ko": "여행 가방",
        "part_of_speech": "noun",
        "pronunciation": "/ˈsuːtkeɪs/",
        "mnemonic": "이 단어를 이렇게 기억해보세요: 'suit'(정장)를 'case'(가방)에 넣는 모습.",
        "example_sentences": [
            {"sentence": "I packed my suitcase.", "translation": "나는 여행 가방을 쌌다."},
            {"sentence": "Her suitcase was too heavy.", "translation": "그녀의 여행 가방은 너무 무거웠다."},
        ],
        "frequency_rank": 2000,
    }
    malformed = {"word": "broken"}

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        assert "여행" in prompt
        return json.dumps([valid, malformed])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_topic_words("beginner", "여행", 2))
    expected = {**valid, "example_sentence": "I packed my suitcase.", "example_translation": "나는 여행 가방을 쌌다."}
    assert result == [expected]


def test_generate_words_raises_on_non_array_response(monkeypatch):
    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps({"not": "an array"})

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    try:
        run(generator.generate_words("beginner", 1))
        assert False, "expected ValueError"
    except ValueError:
        pass
