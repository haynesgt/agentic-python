from typing import Any, Literal

from pydantic import BaseModel
from temporalio import workflow


class TextContent(BaseModel):
    text: str


class BaseAgentEvent(BaseModel):
    type: str
    id: str
    timestamp: float

    # init with generated id and timestamp
    @classmethod
    def create(cls, **data: Any) -> "BaseAgentEvent":
        return cls(
            id=str(workflow.uuid4()),
            timestamp=workflow.now().timestamp(),
            **data,
        )


class QuestionEvent(BaseAgentEvent):
    type: Literal["question"] = "question"
    content: TextContent


class AnswerEvent(BaseAgentEvent):
    type: Literal["answer"] = "answer"
    question_id: str
    content: TextContent


AgentResponseType = AnswerEvent

AgenticEvent = BaseAgentEvent | QuestionEvent | AnswerEvent
