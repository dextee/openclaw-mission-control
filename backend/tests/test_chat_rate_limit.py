# ruff: noqa: INP001
"""Tests for chat-send endpoint rate limiting."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import require_org_admin
from app.api.gateway import router as gateway_router
from app.core import auth as auth_module
from app.core.auth_mode import AuthMode
from app.core.config import settings
from app.db.session import get_session
from app.models.boards import Board
from app.models.gateways import Gateway
from app.models.organizations import Organization
from app.models.organization_members import OrganizationMember
from app.models.users import User
from app.services.organizations import OrganizationContext


async def _make_engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.connect() as conn, conn.begin():
        await conn.run_sync(SQLModel.metadata.create_all)
    return engine


def _build_test_app(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    organization: Organization,
) -> FastAPI:
    app = FastAPI()
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(gateway_router)
    app.include_router(api_v1)

    async def _override_get_session() -> AsyncSession:
        async with session_maker() as session:
            yield session

    async def _override_require_org_admin() -> OrganizationContext:
        return OrganizationContext(
            organization=organization,
            member=OrganizationMember(
                organization_id=organization.id,
                user_id=uuid4(),
                role="owner",
                all_boards_read=True,
                all_boards_write=True,
            ),
        )

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[auth_module.get_session] = _override_get_session
    app.dependency_overrides[require_org_admin] = _override_require_org_admin
    return app


@pytest.mark.asyncio
async def test_chat_send_rate_limit_returns_429_after_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "auth_mode", AuthMode.LOCAL)
    monkeypatch.setattr(settings, "local_auth_token", "chat-rate-limit-token")
    monkeypatch.setattr(auth_module, "LOCAL_AUTH_USER_ID", "chat-test-user")
    monkeypatch.setattr(auth_module, "LOCAL_AUTH_EMAIL", "chat@test.local")
    monkeypatch.setattr(auth_module, "LOCAL_AUTH_NAME", "Chat Test")

    engine = await _make_engine()
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    try:
        async with session_maker() as session:
            organization = Organization(id=uuid4(), name="Test Org")
            gateway = Gateway(
                id=uuid4(),
                organization_id=organization.id,
                name="Test Gateway",
                url="https://gateway.example.local",
                workspace_root="/workspace/openclaw",
            )
            board = Board(
                id=uuid4(),
                organization_id=organization.id,
                gateway_id=gateway.id,
                name="Test Board",
                slug="test-board",
            )
            user = User(
                id=uuid4(),
                clerk_user_id="chat-test-user",
                email="chat@test.local",
                name="Chat Test",
            )
            member = OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
                all_boards_read=True,
                all_boards_write=True,
            )
            session.add(organization)
            session.add(gateway)
            session.add(board)
            session.add(user)
            session.add(member)
            await session.commit()

        app = _build_test_app(session_maker, organization=organization)

        # Mock the actual gateway RPC so no real WebSocket is needed.
        async def _noop(*_args: object, **_kwargs: object) -> None:
            return None

        monkeypatch.setattr(
            "app.services.openclaw.session_service.send_message",
            _noop,
        )
        monkeypatch.setattr(
            "app.services.openclaw.session_service.ensure_session",
            _noop,
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            auth_headers = {"Authorization": "Bearer chat-rate-limit-token"}
            session_id = "test-session-id"
            url = (
                f"/api/v1/gateways/sessions/{session_id}/message"
                f"?board_id={board.id}"
            )
            payload = {"content": "hello"}

            status_codes: list[int] = []
            for _ in range(35):
                response = await client.post(url, json=payload, headers=auth_headers)
                status_codes.append(response.status_code)

            # First 30 should succeed
            assert all(code == 200 for code in status_codes[:30]), (
                f"Expected first 30 to be 200, got: {status_codes[:30]}"
            )
            # At least one of the remaining should be rate-limited
            assert any(code == 429 for code in status_codes[30:]), (
                f"Expected at least one 429 in last 5, got: {status_codes[30:]}"
            )
    finally:
        await engine.dispose()
