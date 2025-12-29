from datetime import timedelta

from temporalio import workflow

from app.activities.agent_pydanticai_activity import get_response
from app.model.agent_event import AgentResponseType, AnswerEvent, QuestionEvent, TextContent


@workflow.defn
class SimpleAgentWorkflow:
    @workflow.run
    async def run(self, question: str) -> AgentResponseType:
        response = await workflow.execute_activity(
            get_response,
            [question_event := QuestionEvent.create(content=TextContent(text=question))],
            schedule_to_close_timeout=timedelta(seconds=20),
        )
        return AnswerEvent.create(question_id=question_event.id, content=TextContent(text=response))
