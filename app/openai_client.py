import openai

from app.config import OPENAI_API_BASE_URL

openai_client = openai.Client(base_url=OPENAI_API_BASE_URL)


def get_openai_client() -> openai.Client:
    return openai_client
