from datetime import timedelta
from logging import getLogger

from temporalio import workflow

from app.activities.agent_pydanticai_activity import get_response
from app.model.agent_event import AgentEvent, AnswerEvent

logger = getLogger(__name__)


@workflow.defn
class AgentWorkflow:
    history: list[AgentEvent]

    def __init__(self):
        self.history = []

    @workflow.run
    async def run(self) -> None:
        workflow.logger.info("Starting AgentWorkflow")
        if not self.history:
            await self.next_event()
        while True:
            workflow.logger.info(f"Current conversation history: {self.history}")
            response: AnswerEvent = await workflow.execute_activity(
                get_response,
                self.history,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self.history.append(response)
            await self.next_event()

    @workflow.update
    async def ask_agent(self, question: str) -> str:
        workflow.logger.info("ask_agent called")
        self.history.append(AgentEvent.create(type="question", content={"text": question}))
        while True:
            event = await self.next_event()
            if event.type == "answer":
                return event.content["text"]

    async def next_event(self) -> AgentEvent:
        last_event = self.history[-1] if self.history else None
        await workflow.wait_condition(lambda: self.history and last_event is not self.history[-1])
        return self.history[-1]
