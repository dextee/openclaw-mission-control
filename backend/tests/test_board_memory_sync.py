# ruff: noqa: S101
"""FIX-20: board memory sync helpers."""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.services.openclaw.board_memory_sync import (
    _flatten_message_text,
    _msg_dedupe_key,
    start_board_memory_sync,
)


def test_dedupe_key_uses_openclaw_id_when_available() -> None:
    msg = {
        "role": "user",
        "content": [{"type": "text", "text": "hi"}],
        "__openclaw": {"id": "a954da54", "seq": 1},
    }
    assert _msg_dedupe_key("agent:foo:main", msg) == "gw:agent:foo:main:a954da54"


def test_dedupe_key_falls_back_to_role_timestamp() -> None:
    msg = {"role": "assistant", "content": [], "timestamp": 1234567890}
    assert _msg_dedupe_key("agent:foo:main", msg) == "gw:agent:foo:main:assistant:1234567890"


def test_flatten_text_message() -> None:
    msg = {"content": [{"type": "text", "text": "hello world"}]}
    assert _flatten_message_text(msg) == "hello world"


def test_flatten_tool_call() -> None:
    msg = {"content": [{"type": "toolCall", "name": "web_search", "arguments": {"q": "x"}}]}
    assert _flatten_message_text(msg) == "[tool:web_search]"


def test_flatten_mixed_content() -> None:
    msg = {
        "content": [
            {"type": "text", "text": "before"},
            {"type": "toolCall", "name": "read"},
            {"type": "text", "text": "after"},
        ]
    }
    assert _flatten_message_text(msg) == "before\n[tool:read]\nafter"


def test_flatten_empty_returns_none() -> None:
    assert _flatten_message_text({"content": []}) is None
    assert _flatten_message_text({}) is None


def test_settings_flag_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_AUTH_TOKEN", "x" * 64)
    s = Settings()
    assert s.mc_memory_sync_enabled is False


def test_settings_flag_can_enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_AUTH_TOKEN", "x" * 64)
    monkeypatch.setenv("MC_MEMORY_SYNC_ENABLED", "true")
    s = Settings()
    assert s.mc_memory_sync_enabled is True


@pytest.mark.asyncio
async def test_start_board_memory_sync_returns_named_task() -> None:
    task = start_board_memory_sync()
    try:
        assert task.get_name() == "board-memory-sync"
        assert not task.done()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
