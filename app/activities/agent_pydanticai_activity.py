from temporalio import activity

from app import config
from app.model.agent_event import AgentEvent, AgentResponseType


@activity.defn
async def get_response(history: list[AgentEvent]) -> AgentResponseType:
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
        output_type=AgentResponseType,
        system_prompt="",
    )
    response = await simple_agent.run(history)
    return response
