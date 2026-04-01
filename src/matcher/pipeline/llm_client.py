"""Shared LLM client factory for all pipeline components."""

from __future__ import annotations

from openai import AsyncOpenAI

from matcher.config import settings


def make_llm_client(
    model_override: str | None = None,
) -> tuple[AsyncOpenAI, str, dict]:
    """Create an OpenAI-compatible client configured for the active LLM provider.

    Args:
        model_override: Use this model instead of settings.llm_model.

    Returns:
        Tuple of (client, model_name, extra_body_kwargs).
    """
    llm_key = settings.active_llm_api_key
    model = model_override or settings.llm_model

    extra_headers: dict[str, str] = {}
    if settings.llm_provider == "openrouter":
        extra_headers["HTTP-Referer"] = "https://matcher.internal"
        extra_headers["X-Title"] = "Sales Nomenclature Matcher"

    client = AsyncOpenAI(
        api_key=llm_key,
        base_url=settings.active_llm_base_url,
        default_headers=extra_headers or None,
        timeout=60.0,
    )
    extra_body: dict = {}

    # Provider-specific native web search enablement
    if settings.llm_provider == "openrouter":
        extra_body["plugins"] = [{"id": "web"}]
    elif settings.llm_provider == "dashscope":
        extra_body["enable_search"] = True
    elif "qwen" in model.lower():
        extra_body["no_thinking"] = True

    return client, model, extra_body


def llm_available() -> bool:
    """Check if an LLM provider is configured with a valid key."""
    key = settings.active_llm_api_key
    return bool(key and key not in ("", "sk-your-key-here", "your-key-here", "none"))


def clean_json_response(content: str) -> str:
    """Strip markdown fences from LLM JSON responses."""
    content = content.strip()
    if content.startswith("```json"):
        content = content.split("```json", 1)[-1].rsplit("```", 1)[0].strip()
    elif content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return content
