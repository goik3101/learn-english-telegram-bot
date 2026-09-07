from app.ai.gemini_client import generate_text

_PROMPT_TEMPLATE = """너는 영어 학습 코치다. 학습자가 아래 영어 텍스트를 직접 한국어로 해석했다.
잘한 점과 다시 확인하면 좋을 부분을 2~3문장으로 자연스럽게 피드백하라. 전체를 대신 번역해주지는 마라.

원문:
{text}

학습자의 해석:
{translation}

피드백 (한국어, 2~3문장, 다른 설명 없이):"""


async def generate_feedback(text: str, translation: str) -> str:
    prompt = _PROMPT_TEMPLATE.format(text=text, translation=translation)
    result = await generate_text(prompt)
    return result.strip()
