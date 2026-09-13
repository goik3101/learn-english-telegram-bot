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
        "mnemonic": "1단계(소리): '애플'은 '아파(아이 아파)'처럼 들림. 2단계(이미지): 사과를 먹다가 배가 아파오는 장면을 상상해보세요.",
        "emoji": "🍎",
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


def _part_question(prompt_sentence: str) -> dict:
    return {
        "topic": "현재완료",
        "concept_intro": "현재완료는 과거에 시작된 일이 현재까지 이어질 때 쓴다.",
        "prompt": prompt_sentence,
        "choices": ["live", "lived", "has lived", "living"],
        "correct_index": 2,
        "explanation": "현재완료 계속 용법",
    }


def test_generate_grammar_questions_for_part_keeps_short_sentence(monkeypatch):
    short = _part_question("She ___ lived here for ten years.")

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps([short])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(
        generator.generate_grammar_questions_for_part(
            "B1", "intermediate", "현재완료", "계속 용법", "설명", 1
        )
    )
    assert len(result) == 1
    assert result[0]["prompt"] == short["prompt"]


def test_generate_grammar_questions_for_part_drops_overly_long_sentence(monkeypatch):
    long_sentence = _part_question(
        "She ___ lived in this exact same small town near the river for more than "
        "ten very long years now, ever since she was a little child."
    )
    short_sentence = _part_question("She ___ lived here for ten years.")

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps([long_sentence, short_sentence])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(
        generator.generate_grammar_questions_for_part(
            "A1", "beginner", "현재완료", "계속 용법", "설명", 2
        )
    )
    assert len(result) == 1
    assert result[0]["prompt"] == short_sentence["prompt"]


def test_generate_topic_words_parses_and_filters_malformed(monkeypatch):
    valid = {
        "word": "suitcase",
        "meaning_ko": "여행 가방",
        "part_of_speech": "noun",
        "pronunciation": "/ˈsuːtkeɪs/",
        "mnemonic": "1단계(소리): '수트케이스'는 '수트 입고 케이스 들기'처럼 들림. 2단계(이미지): 정장을 입고 여행가방을 끄는 모습을 상상해보세요.",
        "emoji": "🧳",
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


def _topic_word(word: str, frequency_rank, meaning_ko: str = "뜻") -> dict:
    return {
        "word": word,
        "meaning_ko": meaning_ko,
        "part_of_speech": "noun",
        "pronunciation": "/test/",
        "mnemonic": "1단계(소리): 테스트. 2단계(이미지): 테스트 장면을 상상해보세요.",
        "emoji": "🔤",
        "example_sentences": [
            {"sentence": f"This is {word}.", "translation": "예문입니다."},
            {"sentence": f"I like {word}.", "translation": "예문입니다."},
        ],
        "frequency_rank": frequency_rank,
    }


def test_generate_topic_words_beginner_word_passes(monkeypatch):
    """실사용 사례 회귀 방지: subsidiary(frequency_rank=6500)처럼 요청 레벨과 명백히 안 맞는
    단어가 beginner 요청에 그대로 통과하면 안 된다 — 이 테스트는 정상 케이스(통과)를 확인."""
    word = _topic_word("dog", 300)

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps([word])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_topic_words("beginner", "일상생활", 1))
    assert [r["word"] for r in result] == ["dog"]


def test_generate_topic_words_rejects_gre_level_word_for_beginner(monkeypatch):
    """subsidiary 실사고 재현: beginner를 요청했는데 AI가 GRE급 단어(frequency_rank=6500)를
    주면 걸러내고, 목표 개수를 못 채웠으면 재시도해야 한다."""
    hard_word = _topic_word("subsidiary", 6500)
    easy_word = _topic_word("dog", 300)
    responses = [json.dumps([hard_word]), json.dumps([easy_word])]
    calls = []

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        calls.append(prompt)
        return responses[len(calls) - 1]

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_topic_words("beginner", "일상생활", 1))

    assert len(calls) == 2  # 1차 응답이 전부 걸러져서 재시도했어야 한다
    assert [r["word"] for r in result] == ["dog"]
    assert "subsidiary" not in [r["word"] for r in result]


def test_generate_topic_words_does_not_reject_easy_word_for_intermediate_request(monkeypatch):
    """intermediate 요청에 beginner 단어가 섞여 나와도 불필요하게 reject하지 않는다(더 쉬운 건
    문제가 아니다 — 요청보다 어려운 경우만 걸러낸다)."""
    easy_word = _topic_word("dog", 300)

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps([easy_word])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_topic_words("intermediate", "일상생활", 1))
    assert [r["word"] for r in result] == ["dog"]


def test_generate_topic_words_does_not_reject_boundary_word(monkeypatch):
    """레벨 경계에 걸친 단어(beginner 밴드 상한 근처)까지 무리하게 reject하지 않는다."""
    boundary_word = _topic_word("boundary", 4500)  # beginner 허용 상한(5000) 아래, 경계 근처

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps([boundary_word])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_topic_words("beginner", "일상생활", 1))
    assert [r["word"] for r in result] == ["boundary"]


def test_generate_topic_words_missing_frequency_rank_is_not_rejected_by_level_check(monkeypatch):
    """frequency_rank가 없으면(형식 자체가 무효라 _is_valid_word에서 걸러지는 것과는 별개로)
    난이도 검증 단계에서 정상 단어를 추가로 깨뜨리지 않는지 확인 — 값이 있는 정상 케이스로
    난이도 검증기가 관대한 방향(fail-open)임을 보인다."""
    from app.vocab import level as vocab_level

    assert vocab_level.is_word_too_hard_for_level(None, "beginner") is False


def test_generate_topic_words_stops_after_max_attempts_without_infinite_loop(monkeypatch):
    """AI가 계속 어려운 단어만 주면 무한 재시도하지 않고 정해진 횟수(2회)만 시도한 뒤
    빈 결과라도 안전하게 반환해야 한다."""
    always_hard = _topic_word("subsidiary", 6500)
    calls = []

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        calls.append(prompt)
        return json.dumps([always_hard])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(generator.generate_topic_words("beginner", "일상생활", 1))

    assert len(calls) == 2  # 정확히 최대 시도 횟수만큼만 호출(무한루프 아님)
    assert result == []  # 계속 실패하면 빈 목록을 안전하게 반환(크래시 없음)


def _reading_item(passage: str) -> dict:
    return {
        "passage": passage,
        "model_translation_ko": "번역",
        "avg_sentence_length": 8,
        "vocab_level": "basic",
        "grammar_complexity": "단순 현재시제",
        "difficulty_band": 1,
    }


def test_reading_passage_within_word_pool_is_accepted_on_first_try(monkeypatch):
    easy_passage = "I like my dog. My dog is happy. We play every day."
    calls = []

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        calls.append(prompt)
        return json.dumps([_reading_item(easy_passage)])

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(
        generator.generate_reading_passage_for_words(
            "beginner", "일상생활", ["dog", "happy", "play"], []
        )
    )

    assert len(calls) == 1  # 단어 목록 안에서 잘 만들었으면 재생성 안 함
    assert result[0]["passage"] == easy_passage


def test_reading_passage_full_of_unknown_words_triggers_one_regeneration(monkeypatch):
    hard_passage = (
        "Ubiquitous algorithmic accountability mechanisms necessitate pragmatic "
        "epistemological considerations regarding institutional legitimacy."
    )
    easier_passage = "I like my dog. My dog is happy. We play every day."
    responses = [json.dumps([_reading_item(hard_passage)]), json.dumps([_reading_item(easier_passage)])]
    calls = []

    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        calls.append(prompt)
        return responses[len(calls) - 1]

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    result = run(
        generator.generate_reading_passage_for_words(
            "beginner", "일상생활", ["dog", "happy", "play"], []
        )
    )

    assert len(calls) == 2  # 미지단어 비율이 너무 높아 한 번 재생성했어야 한다
    assert result[0]["passage"] == easier_passage  # 더 쉬운 재시도 결과를 채택


def test_generate_words_raises_on_non_array_response(monkeypatch):
    async def fake_generate_json(prompt, model="gemini-3.1-flash-lite"):
        return json.dumps({"not": "an array"})

    monkeypatch.setattr(generator, "generate_json", fake_generate_json)

    try:
        run(generator.generate_words("beginner", 1))
        assert False, "expected ValueError"
    except ValueError:
        pass
