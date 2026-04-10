"""Utilities for normalizing zero-token (web) model identifiers."""

from __future__ import annotations

from typing import Literal

# Maps provider prefix -> human-readable name
WEB_PROVIDER_DISPLAY: dict[str, str] = {
    "claude-web": "Claude (Web)",
    "chatgpt-web": "ChatGPT (Web)",
    "gemini-web": "Gemini (Web)",
    "deepseek-web": "DeepSeek (Web)",
    "grok-web": "Grok (Web)",
    "kimi-web": "Kimi (Web)",
    "qwen-web": "Qwen (Web)",
    "qwen-cn-web": "Qwen CN (Web)",
    "glm-web": "GLM (Web)",
    "glm-intl-web": "GLM International (Web)",
    "doubao-web": "Doubao (Web)",
    "perplexity-web": "Perplexity (Web)",
    "xiaomimo-web": "Xiaomi Mo (Web)",
}


def is_web_model(model_id: str) -> bool:
    """Return True if model_id is a zero-token web model."""
    return any(
        model_id.startswith(prefix + "/") or model_id == prefix
        for prefix in WEB_PROVIDER_DISPLAY
    )


def provider_from_model_id(model_id: str) -> str | None:
    """Extract provider prefix from a model id like 'claude-web/claude-sonnet-4-6'."""
    if "/" in model_id:
        return model_id.split("/")[0]
    return model_id if model_id in WEB_PROVIDER_DISPLAY else None


def display_name_for_model(model_id: str) -> str:
    """Return human-readable display name for a model id."""
    provider = provider_from_model_id(model_id)
    if provider and provider in WEB_PROVIDER_DISPLAY:
        model_part = model_id.split("/", 1)[-1] if "/" in model_id else model_id
        return f"{WEB_PROVIDER_DISPLAY[provider]} \u2014 {model_part}"
    return model_id


def provider_type(model_id: str) -> Literal["web", "api"]:
    """Return 'web' for zero-token models, 'api' otherwise."""
    return "web" if is_web_model(model_id) else "api"
