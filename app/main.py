import asyncio
import logging
import os
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker


logger = logging.getLogger("temporal-worker")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)

TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "hello-task-queue")


@activity.defn
async def greet(name: str) -> str:
    """Simple activity that returns a greeting."""
    return f"Hello, {name}!"


@workflow.defn
class HelloWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(
            greet,
            name,
            schedule_to_close_timeout=timedelta(seconds=10),
        )


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


async def worker() -> None:
    """Entry point for running the Temporal worker."""
    await _run_worker()


def server():
    """Placeholder for FastAPI server startup."""
    logger.info("FastAPI server entrypoint not yet implemented.")


if __name__ == "__main__":
    worker()
