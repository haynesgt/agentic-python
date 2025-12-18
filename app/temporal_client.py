import logging

from temporalio.client import Client

from app.config import (
    TEMPORAL_ADDRESS,
    TEMPORAL_NAMESPACE,
    TEMPORAL_TASK_QUEUE,
)

logger = logging.getLogger(__name__)

temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    """Lazy-init Temporal client; reuse across requests."""
    global temporal_client
    if temporal_client is None:
        temporal_client = await Client.connect(
            TEMPORAL_ADDRESS,
            namespace=TEMPORAL_NAMESPACE,
        )
        logger.info(
            "FastAPI connected to Temporal (address=%s, namespace=%s, task_queue=%s)",
            TEMPORAL_ADDRESS,
            TEMPORAL_NAMESPACE,
            TEMPORAL_TASK_QUEUE,
        )
    return temporal_client
