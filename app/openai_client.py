import openai

from app.config import OPENAI_API_BASE_URL

openai_client = openai.Client(base_url=OPENAI_API_BASE_URL)
