"""LLM provider interface.

The agent reasons over an OpenAI-compatible chat API. Groq is the default
(see the hackathon stack), but any provider that speaks the OpenAI protocol
works by changing LLM_PROVIDERS / AGENT_MODEL — no agent code changes.
"""
from functools import lru_cache

from openai import AsyncOpenAI

from ..config import get_settings

LLM_PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
    },
    # Any OpenAI-compatible endpoint (vLLM, LiteLLM proxy, Together, ...)
    "custom": {
        "base_url": "",
        "env_key": "",
    },
}


class LLMNotConfiguredError(RuntimeError):
    """Raised when no API key is present — surfaces as a clear 400 to the UI."""


@lru_cache
def get_llm_client() -> AsyncOpenAI:
    settings = get_settings()
    provider = LLM_PROVIDERS["groq"]  # default provider; swap via code or extend settings
    api_key = settings.groq_api_key
    if not api_key:
        raise LLMNotConfiguredError(
            "No LLM API key configured. Set GROQ_API_KEY in your .env (see .env.example)."
        )
    return AsyncOpenAI(base_url=provider["base_url"], api_key=api_key)


def model_name() -> str:
    return get_settings().agent_model
