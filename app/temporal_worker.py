import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.activities.greet_activity import greet
from app.config import (
    TEMPORAL_ADDRESS,
    TEMPORAL_NAMESPACE,
    TEMPORAL_TASK_QUEUE,
)
from app.workflows.hello_workflow import HelloWorkflow

logger = logging.getLogger(__name__)


async def _run_worker() -> None:
    client = await Client.connect(
        TEMPORAL_ADDRESS,
        namespace=TEMPORAL_NAMESPACE,
    )
    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[HelloWorkflow],
        activities=[greet],
    )
    logger.info(
        "Temporal worker starting (address=%s, namespace=%s, task_queue=%s)",
        TEMPORAL_ADDRESS,
        TEMPORAL_NAMESPACE,
        TEMPORAL_TASK_QUEUE,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_run_worker())
