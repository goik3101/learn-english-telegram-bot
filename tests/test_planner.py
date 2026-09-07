import asyncio

from app import planner


def run(coro):
    return asyncio.run(coro)


def test_returns_none_when_no_weak_topics():
    result = run(planner.build_focus_message("intermediate", [], 0.8))
    assert result is None


def test_returns_generated_message_when_weak_topics_present(monkeypatch):
    async def fake_generate_text(prompt, model="gemini-3.1-flash-lite"):
        assert "가정법" in prompt
        assert "50%" in prompt
        return "  최근 가정법에서 자주 틀리고 있어요. 오늘 집중해봐요!  "

    monkeypatch.setattr(planner, "generate_text", fake_generate_text)

    result = run(planner.build_focus_message("intermediate", ["가정법"], 0.5))
    assert result == "최근 가정법에서 자주 틀리고 있어요. 오늘 집중해봐요!"


def test_returns_none_on_ai_failure(monkeypatch):
    async def failing_generate_text(prompt, model="gemini-3.1-flash-lite"):
        raise RuntimeError("boom")

    monkeypatch.setattr(planner, "generate_text", failing_generate_text)

    result = run(planner.build_focus_message("beginner", ["관계대명사"], None))
    assert result is None
