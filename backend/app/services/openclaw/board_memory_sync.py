"""FIX-20: Background poller that mirrors gateway session history into BoardMemory.

Why this exists:
  Sessions live on the gateway. MC's BoardMemory table is what the UI shows
  for "what was said on this board." Without a sync, anything an agent says
  via the gateway is invisible to MC's memory view, and to any downstream
  consumer that subscribes to BoardMemory events.

Approach:
  Every N seconds, walk all gateway-attached agents on each board and pull
  their session history with a small limit. For each message not yet stored,
  insert a BoardMemory row keyed by a stable `source` derived from the
  gateway's `__openclaw.id` (or a fallback hash of role+timestamp).

Off by default — enable with `MC_MEMORY_SYNC_ENABLED=true`.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import async_session_maker
from app.models.agents import Agent
from app.models.board_memory import BoardMemory
from app.models.gateways import Gateway
from app.services.openclaw.gateway_rpc import (
    GatewayConfig,
    OpenClawGatewayError,
    get_chat_history,
)

logger = get_logger(__name__)

_SYNC_INTERVAL_SECONDS = 30.0
_HISTORY_LIMIT_PER_SESSION = 100
_MAX_SESSIONS_PER_SWEEP = 50


def _msg_dedupe_key(session_id: str, msg: dict[str, Any]) -> str:
    """Stable dedupe key per (session, message) for the BoardMemory.source field."""
    oc = msg.get("__openclaw") or {}
    msg_id = oc.get("id")
    if msg_id:
        return f"gw:{session_id}:{msg_id}"
    ts = msg.get("timestamp")
    role = msg.get("role", "?")
    return f"gw:{session_id}:{role}:{ts}"


def _flatten_message_text(msg: dict[str, Any]) -> str | None:
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif ptype == "toolCall":
            name = part.get("name", "")
            parts.append(f"[tool:{name}]")
        elif ptype == "toolResult":
            parts.append("[tool-result]")
    return "\n".join(parts) if parts else None


async def _existing_source_keys_for_board(
    session: Any,
    board_id: Any,
) -> set[str]:
    statement = select(BoardMemory.source).where(
        col(BoardMemory.board_id) == board_id,
        col(BoardMemory.is_chat) == True,  # noqa: E712 - SQLModel column comparison
        col(BoardMemory.source).is_not(None),
    )
    result = await session.exec(statement)
    return {row for row in result.all() if row}


async def _sync_one_session(
    *,
    session: Any,
    agent: Agent,
    config: GatewayConfig,
    existing_keys: set[str],
) -> int:
    """Fetch one session's history and insert any new messages. Returns # inserted."""
    if agent.openclaw_session_id is None or agent.board_id is None:
        return 0
    try:
        result = await get_chat_history(
            agent.openclaw_session_id,
            config=config,
            limit=_HISTORY_LIMIT_PER_SESSION,
        )
    except OpenClawGatewayError as exc:
        logger.debug(
            "memory_sync.history_fetch_failed",
            extra={"session_id": agent.openclaw_session_id, "error": str(exc)},
        )
        return 0
    if isinstance(result, dict):
        history = result.get("history") or result.get("messages") or []
    elif isinstance(result, list):
        history = result
    else:
        return 0
    inserted = 0
    for msg in history:
        if not isinstance(msg, dict):
            continue
        key = _msg_dedupe_key(agent.openclaw_session_id, msg)
        if key in existing_keys:
            continue
        text = _flatten_message_text(msg)
        if text is None or not text.strip():
            continue
        role = msg.get("role", "?")
        session.add(
            BoardMemory(
                board_id=agent.board_id,
                content=f"[{role}] {text}",
                tags=[f"agent:{agent.id}", f"role:{role}"],
                is_chat=True,
                source=key,
                created_at=utcnow(),
            ),
        )
        existing_keys.add(key)
        inserted += 1
    if inserted:
        await session.commit()
    return inserted


async def _run_one_sweep() -> int:
    """One pass: returns total inserted rows."""
    total = 0
    async with async_session_maker() as session:
        # Pick agents that have a session and a board, capping for safety.
        statement = (
            select(Agent)
            .where(col(Agent.openclaw_session_id).is_not(None))
            .where(col(Agent.board_id).is_not(None))
            .where(col(Agent.gateway_id).is_not(None))
            .where(col(Agent.status).in_(["online", "updating", "provisioning"]))
            .order_by(func.coalesce(Agent.last_seen_at, Agent.created_at).desc())
            .limit(_MAX_SESSIONS_PER_SWEEP)
        )
        agents = list((await session.exec(statement)).all())
        gateway_cache: dict[Any, GatewayConfig] = {}
        existing_per_board: dict[Any, set[str]] = {}
        for agent in agents:
            if agent.gateway_id not in gateway_cache:
                gw = await Gateway.objects.by_id(agent.gateway_id).first(session)
                if gw is None:
                    continue
                gateway_cache[agent.gateway_id] = GatewayConfig(
                    url=gw.url,
                    token=gw.token,
                    allow_insecure_tls=gw.allow_insecure_tls,
                    disable_device_pairing=gw.disable_device_pairing,
                )
            if agent.board_id not in existing_per_board:
                existing_per_board[agent.board_id] = await _existing_source_keys_for_board(
                    session,
                    agent.board_id,
                )
            inserted = await _sync_one_session(
                session=session,
                agent=agent,
                config=gateway_cache[agent.gateway_id],
                existing_keys=existing_per_board[agent.board_id],
            )
            total += inserted
    return total


async def _run_loop() -> None:
    while True:
        try:
            inserted = await _run_one_sweep()
            if inserted:
                logger.info("memory_sync.sweep_completed", extra={"inserted": inserted})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            logger.exception("memory_sync.sweep_error", extra={"error": str(exc)})
        await asyncio.sleep(_SYNC_INTERVAL_SECONDS)


def start_board_memory_sync() -> asyncio.Task[None]:
    return asyncio.create_task(_run_loop(), name="board-memory-sync")
