import os

TEMPORAL_ADDRESS = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
TEMPORAL_NAMESPACE = os.getenv("TEMPORAL_NAMESPACE", "default")
TEMPORAL_TASK_QUEUE = os.getenv("TEMPORAL_TASK_QUEUE", "hello-task-queue")

OPENAI_ADDRESS = os.getenv("OPENAI_ADDRESS", "http://localhost:8150/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")
