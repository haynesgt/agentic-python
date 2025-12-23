from datetime import timedelta

from temporalio import workflow

from app.activities.agent_pydanticai_activity import get_response
from app.model.agent_event import AgentEvent, AnswerEvent


@workflow.defn
class AgentWorkflow:
    history: list[AgentEvent]

    def __init__(self):
        self.history = []

    @workflow.run
    async def run(self) -> None:
        while True:
            await self.next_event()
            response: AnswerEvent = await workflow.execute_activity(
                get_response,
                self.history,
                start_to_close_timeout=timedelta(seconds=10),
            )
            self.history.append(response)

    @workflow.update
    async def ask_agent(self, question: str) -> str:
        self.history.append(AgentEvent.create(type="question", content={"text": question}))
        while True:
            event = await self.next_event()
            if event.type == "answer":
                return event.content["text"]

    async def next_event(self) -> AgentEvent:
        last_event = self.history[-1] if self.history else None
        await workflow.wait_condition(lambda: self.history and last_event is not self.history[-1])
        return self.history[-1]
