"""FIX-19: Periodic background task that recovers agents stuck in `provisioning`.

When the initial `run_lifecycle` call fails between writing the DB row and
finishing the gateway side (server crash, network blip, client disconnect),
the agent record is left with `status="provisioning"` and `last_seen_at=None`
forever. This module runs a periodic sweep that re-attempts the lifecycle for
those orphans, capped at `MAX_WAKE_ATTEMPTS_WITHOUT_CHECKIN` per agent so we
don't burn gateway resources on permanently broken configs.

Disable via `MC_STUCK_PROVISIONING_RECONCILER_ENABLED=false`.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlmodel import col, select

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.agents import Agent
from app.models.boards import Board
from app.models.gateways import Gateway
from app.services.openclaw.constants import MAX_WAKE_ATTEMPTS_WITHOUT_CHECKIN
from app.services.openclaw.lifecycle_orchestrator import AgentLifecycleOrchestrator

logger = get_logger(__name__)

_STUCK_PROVISIONING_THRESHOLD = timedelta(minutes=5)
_RECONCILER_INTERVAL_SECONDS = 120.0
_PER_AGENT_RECONCILE_TIMEOUT_S = 60.0


async def _find_stuck_agents() -> list[Agent]:
    """Return agents that look stuck in `provisioning` past the threshold."""
    cutoff = utcnow() - _STUCK_PROVISIONING_THRESHOLD
    async with async_session_maker() as session:
        statement = (
            select(Agent)
            .where(col(Agent.status) == "provisioning")
            .where(col(Agent.last_seen_at).is_(None))
            .where(col(Agent.created_at) < cutoff)
            .where(col(Agent.wake_attempts) < MAX_WAKE_ATTEMPTS_WITHOUT_CHECKIN)
            .where(col(Agent.gateway_id).is_not(None))
        )
        result = await session.exec(statement)
        return list(result.all())


async def _reconcile_one(agent_id: object) -> None:
    """Re-run lifecycle for a single stuck agent, in its own session."""
    async with async_session_maker() as session:
        agent = await Agent.objects.by_id(agent_id).first(session)
        if agent is None:
            return
        gateway = await Gateway.objects.by_id(agent.gateway_id).first(session)
        if gateway is None:
            logger.warning(
                "stuck_provisioning.skip_missing_gateway",
                extra={"agent_id": str(agent.id), "gateway_id": str(agent.gateway_id)},
            )
            return
        board: Board | None = None
        if agent.board_id is not None:
            board = await Board.objects.by_id(agent.board_id).first(session)
            if board is None:
                logger.warning(
                    "stuck_provisioning.skip_missing_board",
                    extra={"agent_id": str(agent.id), "board_id": str(agent.board_id)},
                )
                return
        try:
            await asyncio.wait_for(
                AgentLifecycleOrchestrator(session).run_lifecycle(
                    gateway=gateway,
                    agent_id=agent.id,
                    board=board,
                    user=None,
                    action="update",
                    wake=True,
                    deliver_wakeup=True,
                    wakeup_verb="provisioned",
                    raise_gateway_errors=False,
                ),
                timeout=_PER_AGENT_RECONCILE_TIMEOUT_S,
            )
            logger.info(
                "stuck_provisioning.reconciled",
                extra={"agent_id": str(agent.id)},
            )
        except (TimeoutError, RuntimeError, ValueError) as exc:
            logger.warning(
                "stuck_provisioning.reconcile_failed",
                extra={"agent_id": str(agent.id), "error": str(exc)},
            )


async def _run_loop() -> None:
    while True:
        try:
            stuck = await _find_stuck_agents()
            if stuck:
                logger.info(
                    "stuck_provisioning.sweep_starting",
                    extra={"count": len(stuck)},
                )
                for agent in stuck:
                    await _reconcile_one(agent.id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep loop alive on unexpected errors
            logger.exception(
                "stuck_provisioning.sweep_error",
                extra={"error": str(exc)},
            )
        await asyncio.sleep(_RECONCILER_INTERVAL_SECONDS)


def start_stuck_provisioning_reconciler() -> asyncio.Task[None]:
    """Spawn the background sweep. Cancel the returned task on shutdown."""
    return asyncio.create_task(
        _run_loop(),
        name="stuck-provisioning-reconciler",
    )
