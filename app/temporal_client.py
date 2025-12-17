import asyncio
import logging
import os
from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

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
