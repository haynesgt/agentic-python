from collections.abc import Callable
from datetime import UTC, datetime
from logging import getLogger

import logfire
from logfire_api import ConsoleOptions
from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

import app.config as config

"""
    colors: ConsoleColorsValues = ...
    span_style: Literal['simple', 'indented', 'show-parents'] = ...
    include_timestamps: bool = ...
    include_tags: bool = ...
    verbose: bool = ...
    min_log_level: LevelName = ...
    show_project_link: bool = ...
    output: TextIO | None = ...
"""
logfire.configure(
    send_to_logfire=False,
    console=ConsoleOptions(
        include_timestamps=True,
        min_log_level="trace",
        verbose=True,
    ),
)
logfire.instrument_pydantic_ai()

logger = getLogger(__name__)


class SimpleAgentDeps(BaseModel):
    handle_response: Callable[[str], None]


class SimpleAgentResponse(BaseModel):
    message: str


model = OpenAIChatModel(
    config.OPENAI_MODEL,
    provider=OpenAIProvider(
        base_url=config.OPENAI_API_BASE_URL,
        api_key=config.OPENAI_API_KEY,
    ),
)
simple_agent = Agent(
    model,
    output_type=None,
    system_prompt="Use send_response for the response to the original message",
)


@simple_agent.tool
def get_time(arg):
    logger.info("getting time")
    return datetime.now(UTC).isoformat()


@simple_agent.tool
def send_response(ctx: RunContext[SimpleAgentDeps], message: str):
    ctx.deps.handle_response(message)
