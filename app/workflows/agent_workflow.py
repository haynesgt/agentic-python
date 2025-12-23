import uuid
from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from temporalio import workflow

from app import config

model = OpenAIChatModel(
    config.OPENAI_MODEL,
    provider=OpenAIProvider(
        base_url=config.OPENAI_API_BASE_URL,
        api_key=config.OPENAI_API_KEY,
    ),
)


class Event(BaseModel):
    type: str
    id: str
    timestamp: float
    content: Any

    @classmethod
    def create(cls, type: str, content: Any) -> "Event":
        return cls(
            type=type, id=str(uuid.uuid4()), timestamp=workflow.now().timestamp(), content=content
        )


@workflow.defn
class AgentWorkflow:
    history: list[Event]

    def __init__(self):
        self.simple_agent = Agent(
            model,
            output_type=Event,
            system_prompt="",
        )
        self.history = []

    @workflow.run
    async def run(self) -> None:
        while True:
            await self.next_event()
            response = await self.simple_agent.run(self.history)
            self.history.append(response)

    @workflow.update
    async def ping(self) -> str:
        return "pong"

    @workflow.update
    async def ask_agent(self, question: str) -> str:
        self.history.append(Event.create(type="question", content={"text": question}))
        while True:
            event = await self.next_event()
            if event.type == "answer":
                return event.content["text"]

    async def next_event(self) -> Event:
        last_event = self.history[-1] if self.history else None
        await workflow.wait_condition(lambda: last_event is not self.history[-1])
        return self.history[-1]
