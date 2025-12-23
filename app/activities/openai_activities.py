from temporalio import activity

from ..config import OPENAI_MODEL
from ..openai_client import get_openai_client


@activity.defn
async def call_openai_api(prompt: str) -> str:
    """Activity that calls the OpenAI API with a given prompt."""
    client = get_openai_client()
    response = await client.responses.create(
        model=OPENAI_MODEL,
        prompt=prompt,
    )
    return response.output[0].content[0].text
