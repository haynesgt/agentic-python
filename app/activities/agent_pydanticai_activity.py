import json
from functools import lru_cache

from temporalio import activity

from app import config


@lru_cache
def get_agent():
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    model = OpenAIChatModel(
        config.OPENAI_MODEL,
        provider=OpenAIProvider(
            base_url=config.OPENAI_API_BASE_URL,
            api_key=config.OPENAI_API_KEY,
        ),
    )
    simple_agent = Agent(
        model,
        system_prompt="You will be given a list of events that happened to the model. Take actions as needed and return a response if necessary.",
    )
    return simple_agent


@activity.defn
async def get_response(history: list[dict]) -> str:
    response = await get_agent().run(json.dumps(history))  # util.dumps(history))
    return response.output
