"""Schemas for gateway passthrough API request and response payloads."""

from __future__ import annotations

from typing import Literal

from sqlmodel import SQLModel

from app.schemas.common import NonEmptyStr

RUNTIME_ANNOTATION_TYPES = (NonEmptyStr,)


class GatewaySessionMessageRequest(SQLModel):
    """Request payload for sending a message into a gateway session."""

    content: NonEmptyStr


class GatewayResolveQuery(SQLModel):
    """Query parameters used to resolve which gateway to target."""

    board_id: str | None = None
    gateway_url: str | None = None
    gateway_token: str | None = None
    gateway_disable_device_pairing: bool | None = None
    gateway_allow_insecure_tls: bool | None = None


class GatewaysStatusResponse(SQLModel):
    """Aggregated gateway status response including session metadata."""

    connected: bool
    gateway_url: str
    sessions_count: int | None = None
    sessions: list[object] | None = None
    main_session: object | None = None
    main_session_error: str | None = None
    error: str | None = None


class GatewaySessionsResponse(SQLModel):
    """Gateway sessions list response payload."""

    sessions: list[object]
    main_session: object | None = None


class GatewaySessionResponse(SQLModel):
    """Single gateway session response payload."""

    session: object


class GatewaySessionHistoryResponse(SQLModel):
    """Gateway session history response payload."""

    history: list[object]


class GatewayCommandsResponse(SQLModel):
    """Gateway command catalog and protocol metadata."""

    protocol_version: int
    methods: list[str]
    events: list[str]


class BrowserContextStatus(SQLModel):
    """Browser context health for a single zero-token provider."""

    provider: str
    healthy: bool
    cdp_connected: bool
    last_checked_at: int | None = None


class BrowserStatusResponse(SQLModel):
    """Aggregate browser context health response."""

    contexts: list[BrowserContextStatus]
    error: str | None = None


class ChannelAuthStatus(SQLModel):
    """Auth validity state for a single channel."""

    channel_id: str
    auth_valid: bool
    needs_reauth: bool
    cookie_expiry: int | None = None
    provider_type: Literal["web", "api"] = "api"


class ChannelsAuthStatusResponse(SQLModel):
    """Aggregate auth status for all channels."""

    channels: list[ChannelAuthStatus]
    error: str | None = None


class ChannelReauthRequest(SQLModel):
    """Request to trigger reauth for a specific channel."""

    channel_id: str


class ChannelReauthResponse(SQLModel):
    """Response from channel reauth operation."""

    status: Literal["pending", "ok", "error"]
    auth_url: str | None = None
    channel_id: str
    error: str | None = None
