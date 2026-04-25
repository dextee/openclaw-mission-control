# ruff: noqa: S101
"""FIX-19: stuck-provisioning reconciler module shape + flag."""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.services.openclaw.stuck_provisioning_reconciler import (
    _RECONCILER_INTERVAL_SECONDS,
    _STUCK_PROVISIONING_THRESHOLD,
    start_stuck_provisioning_reconciler,
)


def test_thresholds_are_sane() -> None:
    # The threshold must be longer than the typical provisioning round-trip
    # (~few seconds) but short enough that orphans recover within a UI session.
    assert _STUCK_PROVISIONING_THRESHOLD.total_seconds() >= 60
    assert _STUCK_PROVISIONING_THRESHOLD.total_seconds() <= 600
    # Sweep cadence must be reasonable: not so often it spams gateway,
    # not so rare that orphans linger.
    assert 30 <= _RECONCILER_INTERVAL_SECONDS <= 600


@pytest.mark.asyncio
async def test_start_stuck_provisioning_reconciler_returns_task() -> None:
    task = start_stuck_provisioning_reconciler()
    try:
        assert isinstance(task, asyncio.Task)
        assert task.get_name() == "stuck-provisioning-reconciler"
        assert not task.done()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_settings_flag_defaults_on(monkeypatch: pytest.MonkeyPatch) -> None:
    # Make sure the flag exists with the documented default. Production users
    # rely on this being default-on for the recovery behavior.
    monkeypatch.setenv("LOCAL_AUTH_TOKEN", "x" * 64)
    s = Settings()
    assert s.mc_stuck_provisioning_reconciler_enabled is True


def test_settings_flag_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_AUTH_TOKEN", "x" * 64)
    monkeypatch.setenv("MC_STUCK_PROVISIONING_RECONCILER_ENABLED", "false")
    s = Settings()
    assert s.mc_stuck_provisioning_reconciler_enabled is False
