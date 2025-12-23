import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import temporalio.common
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic_ai.result import StreamedRunResult
from temporalio.client import WithStartWorkflowOperation

from app.config import (
    OPENAI_MODEL,
    TEMPORAL_TASK_QUEUE,
)
from app.openai_client import openai_client
from app.simple_agent import SimpleAgentDeps, simple_agent
from app.temporal_client import get_temporal_client, temporal_client
from app.workflows.hello_workflow import HelloWorkflow

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


@app.get("/ai-agent")
async def get_ai_agent_response(query: str) -> str | None:
    response_event = asyncio.get_running_loop().create_future()
    agent_run = simple_agent.run(
        query, deps=SimpleAgentDeps(handle_response=response_event.set_result)
    )
    asyncio.create_task(agent_run)
    return await response_event


@app.get("/ai-agent-stream")
async def get_ai_agent_stream_response(query: str):
    response_event = asyncio.get_running_loop().create_future()

    def handle_response(message: str):
        logger.info(f"Final response: {message}")
        if not response_event.done():
            response_event.set_result(message)

    class MyOutput(BaseModel):
        chunk: str

    async def gen():
        from pydantic_ai import Agent

        agent = Agent(simple_agent.model)
        async with agent.run_stream(
            query, deps=SimpleAgentDeps(handle_response=handle_response)
        ) as stream:
            if TYPE_CHECKING:
                stream: StreamedRunResult[MyOutput]
            async for chunk in stream.stream_text(delta=True, debounce_by=0.01):
                yield chunk

    return StreamingResponse(gen(), media_type="text/plain")


@app.get("/agent-workflow")
async def get_agent_workflow_response(query: str) -> str | None:
    from app.workflows.agent_workflow import AgentWorkflow

    workflow_result = await (await get_temporal_client()).execute_update_with_start_workflow(
        AgentWorkflow.ask_agent,
        args=[query],
        start_workflow_operation=WithStartWorkflowOperation(
            AgentWorkflow.run,
            id=f"agent-workflow-{uuid4()}",
            id_conflict_policy=temporalio.common.WorkflowIDConflictPolicy.USE_EXISTING,
            task_queue=TEMPORAL_TASK_QUEUE,
            execution_timeout=timedelta(seconds=20),
        ),
    )

    return workflow_result
