"""
Single place to construct the LLM client, so switching providers (OpenAI,
Groq, or any other OpenAI-compatible API) only requires changing .env.
"""
from openai import OpenAI

from app.config import settings


def get_llm_client() -> OpenAI:
    kwargs = {"api_key": settings.openai_api_key}
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**kwargs)