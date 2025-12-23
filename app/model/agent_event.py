from typing import Any

from pydantic import BaseModel
from temporalio import workflow


class AgentEvent(BaseModel):
    type: str
    id: str
    timestamp: float
    content: Any

    @classmethod
    def create(cls, type: str, content: Any) -> "AgentEvent":
        return cls(
            type=type,
            id=str(workflow.uuid4()),
            timestamp=workflow.now().timestamp(),
            content=content,
        )


class QuestionEvent(AgentEvent):
    type: str = "question"
    content: dict[str, str]


class AnswerEvent(AgentEvent):
    type: str = "answer"
    question_id: str
    content: dict[str, str]


AgentResponseType = AnswerEvent
