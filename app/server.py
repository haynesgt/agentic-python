import logging
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import (
    OPENAI_MODEL,
    TEMPORAL_TASK_QUEUE,
)
from app.temporal_client import get_temporal_client, temporal_client
from app.workflows import HelloWorkflow

from .openai_client import openai_client

logger = logging.getLogger(__name__)


class HelloRequest(BaseModel):
    name: str = "world"


class HelloResponse(BaseModel):
    workflow_id: str
    message: str


async def lifespan(app: FastAPI):
    yield
    if temporal_client is not None:
        await temporal_client.close()


app = FastAPI(title="Agentic API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/hello", response_model=HelloResponse)
async def start_hello_workflow(name: str) -> HelloResponse:
    client = await get_temporal_client()
    workflow_id = f"hello-{uuid4()}"
    handle = await client.start_workflow(
        HelloWorkflow.run,
        name,
        id=workflow_id,
        task_queue=TEMPORAL_TASK_QUEUE,
    )
    message = await handle.result()
    return HelloResponse(workflow_id=workflow_id, message=message)


@app.get("/ai/{path}", response_model=HelloResponse)
async def get_ai_response(path: str) -> HelloResponse:
    response = openai_client.responses.create(
        model=OPENAI_MODEL,
        input=path,
    )
    return HelloResponse(workflow_id="n/a", message=response.output[0].content[0].text)
