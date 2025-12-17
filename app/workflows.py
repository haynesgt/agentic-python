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

from app.activities import greet

@workflow.defn
class HelloWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        return await workflow.execute_activity(
            greet,
            name,
            schedule_to_close_timeout=timedelta(seconds=10),
        )
