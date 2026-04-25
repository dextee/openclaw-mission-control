# ruff: noqa: S101
"""FIX-18: with_computed_status timeouts for transitional states."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from app.core.time import utcnow
from app.models.agents import Agent
from app.services.openclaw.constants import OFFLINE_AFTER, UPDATING_STATE_TIMEOUT
from app.services.openclaw.provisioning_db import AgentLifecycleService


def _agent(*, status: str, last_seen_at=None, updated_age: timedelta | None = None) -> Agent:
    now = utcnow()
    updated_at = now - updated_age if updated_age else now
    return Agent(
        id=uuid4(),
        gateway_id=uuid4(),
        organization_id=uuid4(),
        name="test",
        status=status,
        last_seen_at=last_seen_at,
        updated_at=updated_at,
    )


def test_updating_under_timeout_stays_updating() -> None:
    a = _agent(status="updating", updated_age=UPDATING_STATE_TIMEOUT - timedelta(seconds=10))
    out = AgentLifecycleService.with_computed_status(a)
    assert out.status == "updating"


def test_updating_past_timeout_reverts_to_offline() -> None:
    a = _agent(status="updating", updated_age=UPDATING_STATE_TIMEOUT + timedelta(seconds=10))
    out = AgentLifecycleService.with_computed_status(a)
    assert out.status == "offline"


def test_deleting_is_never_reverted() -> None:
    a = _agent(status="deleting", updated_age=timedelta(hours=24))
    out = AgentLifecycleService.with_computed_status(a)
    assert out.status == "deleting"


def test_no_last_seen_at_means_provisioning() -> None:
    a = _agent(status="online", last_seen_at=None)
    out = AgentLifecycleService.with_computed_status(a)
    assert out.status == "provisioning"


def test_recent_last_seen_stays_online() -> None:
    a = _agent(status="online", last_seen_at=utcnow() - timedelta(seconds=30))
    out = AgentLifecycleService.with_computed_status(a)
    assert out.status == "online"


def test_stale_last_seen_flips_offline() -> None:
    a = _agent(status="online", last_seen_at=utcnow() - OFFLINE_AFTER - timedelta(seconds=30))
    out = AgentLifecycleService.with_computed_status(a)
    assert out.status == "offline"
