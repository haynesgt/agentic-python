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

@activity.defn
async def greet(name: str) -> str:
    """Simple activity that returns a greeting."""
    return f"Hello, {name}!"
