"""Tests for zero-token gateway extensions."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.gateway_api import (
    BrowserStatusResponse,
    ChannelsAuthStatusResponse,
    ChannelReauthResponse,
)
from app.services.openclaw.web_model_utils import (
    display_name_for_model,
    is_web_model,
    provider_from_model_id,
)


# --- web_model_utils unit tests ---


def test_is_web_model_true() -> None:
    assert is_web_model("claude-web/claude-sonnet-4-6") is True
    assert is_web_model("chatgpt-web/gpt-4") is True
    assert is_web_model("deepseek-web") is True


def test_is_web_model_false() -> None:
    assert is_web_model("claude-3-opus-20240229") is False
    assert is_web_model("gpt-4-turbo") is False


def test_display_name_for_model_web() -> None:
    result = display_name_for_model("claude-web/claude-sonnet-4-6")
    assert "Claude (Web)" in result
    assert "claude-sonnet-4-6" in result


def test_display_name_for_model_api() -> None:
    result = display_name_for_model("gpt-4-turbo")
    assert result == "gpt-4-turbo"


def test_provider_from_model_id() -> None:
    assert provider_from_model_id("claude-web/claude-sonnet-4-6") == "claude-web"
    assert provider_from_model_id("gpt-4") is None


# --- BrowserStatusResponse schema ---


def test_browser_status_response_empty() -> None:
    resp = BrowserStatusResponse(contexts=[])
    assert resp.contexts == []
    assert resp.error is None


def test_browser_status_response_with_error() -> None:
    resp = BrowserStatusResponse(contexts=[], error="gateway unreachable")
    assert resp.error == "gateway unreachable"


# --- ChannelReauthResponse schema ---


def test_channel_reauth_response_pending() -> None:
    resp = ChannelReauthResponse(
        status="pending",
        auth_url="https://claude.ai/login",
        channel_id="claude-web",
    )
    assert resp.status == "pending"
    assert resp.auth_url is not None


def test_channel_reauth_response_ok() -> None:
    resp = ChannelReauthResponse(status="ok", channel_id="claude-web")
    assert resp.status == "ok"
    assert resp.auth_url is None


# --- ChannelsAuthStatusResponse schema ---


def test_channels_auth_status_response_empty() -> None:
    resp = ChannelsAuthStatusResponse(channels=[])
    assert resp.channels == []
    assert resp.error is None


def test_channel_auth_status_web() -> None:
    status = ChannelsAuthStatusResponse(
        channels=[
            {
                "channel_id": "qwen-web",
                "auth_valid": True,
                "needs_reauth": False,
                "cookie_expiry": None,
                "provider_type": "web",
            }
        ]
    )
    assert len(status.channels) == 1
    assert status.channels[0].channel_id == "qwen-web"
    assert status.channels[0].provider_type == "web"
