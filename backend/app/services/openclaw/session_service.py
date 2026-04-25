"""Gateway session query service."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from fastapi import HTTPException, status

from app.core.logging import TRACE_LEVEL
from app.models.boards import Board
from app.models.gateways import Gateway
from app.schemas.gateway_api import (
    BrowserContextStatus,
    BrowserStatusResponse,
    ChannelAuthStatus,
    ChannelReauthResponse,
    ChannelsAuthStatusResponse,
    GatewayModelItem,
    GatewayModelsResponse,
    GatewayResolveQuery,
    GatewaySessionHistoryResponse,
    GatewaySessionMessageRequest,
    GatewaySessionResponse,
    GatewaySessionsResponse,
    GatewaysStatusResponse,
)
from app.services.openclaw.db_service import OpenClawDBService
from app.services.openclaw.error_messages import normalize_gateway_error_message
from app.services.openclaw.gateway_compat import check_gateway_version_compatibility
from app.services.openclaw.gateway_resolver import gateway_client_config, require_gateway_for_board
from app.services.openclaw.gateway_rpc import GatewayConfig as GatewayClientConfig
from app.services.openclaw.gateway_rpc import (
    OpenClawGatewayError,
    ensure_session,
    get_chat_history,
    openclaw_call,
    send_message,
)
from app.services.openclaw.policies import OpenClawAuthorizationPolicy
from app.services.openclaw.shared import GatewayAgentIdentity
from app.services.organizations import require_board_access

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.models.users import User


@dataclass(frozen=True, slots=True)
class GatewayTemplateSyncQuery:
    """Sync options parsed from query args for gateway template operations."""

    include_main: bool
    lead_only: bool
    reset_sessions: bool
    rotate_tokens: bool
    force_bootstrap: bool
    overwrite: bool
    board_id: UUID | None


class GatewaySessionService(OpenClawDBService):
    """Read/query gateway runtime session state for user-facing APIs."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    @staticmethod
    def to_resolve_query(
        board_id: UUID | None,
        gateway_url: str | None,
        gateway_token: str | None,
        gateway_disable_device_pairing: bool | None = None,
        gateway_allow_insecure_tls: bool | None = None,
    ) -> GatewayResolveQuery:
        return GatewayResolveQuery(
            board_id=board_id,
            gateway_url=gateway_url,
            gateway_token=gateway_token,
            gateway_disable_device_pairing=gateway_disable_device_pairing,
            gateway_allow_insecure_tls=gateway_allow_insecure_tls,
        )

    @staticmethod
    def as_object_list(value: object) -> list[object]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, (tuple, set)):
            return list(value)
        if isinstance(value, (str, bytes, dict)):
            return []
        if isinstance(value, Iterable):
            return list(value)
        return []

    async def resolve_gateway(
        self,
        params: GatewayResolveQuery,
        *,
        user: User | None = None,
        organization_id: UUID | None = None,
    ) -> tuple[Board | None, GatewayClientConfig, str | None]:
        self.logger.log(
            TRACE_LEVEL,
            "gateway.resolve.start board_id=%s gateway_url=%s",
            params.board_id,
            params.gateway_url,
        )
        if params.gateway_url:
            raw_url = params.gateway_url.strip()
            if not raw_url:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="board_id or gateway_url is required",
                )
            token = (params.gateway_token or "").strip() or None
            gateway: Gateway | None = None
            can_query_saved_gateway = organization_id is not None and hasattr(self.session, "exec")
            if can_query_saved_gateway and (
                params.gateway_allow_insecure_tls is None
                or params.gateway_disable_device_pairing is None
            ):
                gateway_query = Gateway.objects.filter_by(url=raw_url)
                if organization_id is not None:
                    gateway_query = gateway_query.filter_by(organization_id=organization_id)
                gateway = await gateway_query.first(self.session)
            allow_insecure_tls = (
                params.gateway_allow_insecure_tls
                if params.gateway_allow_insecure_tls is not None
                else (gateway.allow_insecure_tls if gateway is not None else False)
            )
            disable_device_pairing = (
                params.gateway_disable_device_pairing
                if params.gateway_disable_device_pairing is not None
                else (gateway.disable_device_pairing if gateway is not None else False)
            )
            return (
                None,
                GatewayClientConfig(
                    url=raw_url,
                    token=token,
                    allow_insecure_tls=allow_insecure_tls,
                    disable_device_pairing=disable_device_pairing,
                ),
                None,
            )
        if not params.board_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="board_id or gateway_url is required",
            )
        board = await Board.objects.by_id(params.board_id).first(self.session)
        if board is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Board not found",
            )
        if user is not None:
            await require_board_access(self.session, user=user, board=board, write=False)
        gateway = await require_gateway_for_board(self.session, board)
        config = gateway_client_config(gateway)
        main_session = GatewayAgentIdentity.session_key(gateway)
        return (
            board,
            config,
            main_session,
        )

    async def require_gateway(
        self,
        board_id: UUID | None,
        *,
        user: User | None = None,
    ) -> tuple[Board, GatewayClientConfig, str | None]:
        params = GatewayResolveQuery(board_id=board_id)
        board, config, main_session = await self.resolve_gateway(params, user=user)
        if board is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="board_id is required",
            )
        return board, config, main_session

    async def list_sessions(self, config: GatewayClientConfig) -> list[dict[str, object]]:
        sessions = await openclaw_call("sessions.list", config=config)
        if isinstance(sessions, dict):
            raw_items = self.as_object_list(sessions.get("sessions"))
        else:
            raw_items = self.as_object_list(sessions)
        return [item for item in raw_items if isinstance(item, dict)]

    async def with_main_session(
        self,
        sessions_list: list[dict[str, object]],
        *,
        config: GatewayClientConfig,
        main_session: str | None,
    ) -> list[dict[str, object]]:
        if not main_session or any(item.get("key") == main_session for item in sessions_list):
            return sessions_list
        try:
            await ensure_session(main_session, config=config, label="Gateway Agent")
            return await self.list_sessions(config)
        except OpenClawGatewayError:
            return sessions_list

    @staticmethod
    def _require_same_org(board: Board | None, organization_id: UUID) -> None:
        if board is None:
            return
        OpenClawAuthorizationPolicy.require_board_write_access(
            allowed=board.organization_id == organization_id,
        )

    async def get_status(
        self,
        *,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> GatewaysStatusResponse:
        board, config, main_session = await self.resolve_gateway(
            params,
            user=user,
            organization_id=organization_id,
        )
        self._require_same_org(board, organization_id)
        try:
            compatibility = await check_gateway_version_compatibility(config)
        except OpenClawGatewayError as exc:
            return GatewaysStatusResponse(
                connected=False,
                gateway_url=config.url,
                error=normalize_gateway_error_message(str(exc)),
            )
        if not compatibility.compatible:
            return GatewaysStatusResponse(
                connected=False,
                gateway_url=config.url,
                error=compatibility.message,
            )
        try:
            sessions = await openclaw_call("sessions.list", config=config)
            if isinstance(sessions, dict):
                sessions_list = self.as_object_list(sessions.get("sessions"))
            else:
                sessions_list = self.as_object_list(sessions)
            main_session_entry: object | None = None
            main_session_error: str | None = None
            if main_session:
                try:
                    ensured = await ensure_session(
                        main_session,
                        config=config,
                        label="Gateway Agent",
                    )
                    if isinstance(ensured, dict):
                        main_session_entry = ensured.get("entry") or ensured
                except OpenClawGatewayError as exc:
                    main_session_error = str(exc)
            return GatewaysStatusResponse(
                connected=True,
                gateway_url=config.url,
                sessions_count=len(sessions_list),
                sessions=sessions_list,
                main_session=main_session_entry,
                main_session_error=main_session_error,
            )
        except OpenClawGatewayError as exc:
            return GatewaysStatusResponse(
                connected=False,
                gateway_url=config.url,
                error=normalize_gateway_error_message(str(exc)),
            )

    async def get_sessions(
        self,
        *,
        board_id: UUID | None,
        organization_id: UUID,
        user: User | None,
    ) -> GatewaySessionsResponse:
        params = GatewayResolveQuery(board_id=board_id)
        board, config, main_session = await self.resolve_gateway(params, user=user)
        self._require_same_org(board, organization_id)
        try:
            sessions = await openclaw_call("sessions.list", config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        if isinstance(sessions, dict):
            sessions_list = self.as_object_list(sessions.get("sessions"))
        else:
            sessions_list = self.as_object_list(sessions)

        main_session_entry: object | None = None
        if main_session:
            try:
                ensured = await ensure_session(
                    main_session,
                    config=config,
                    label="Gateway Agent",
                )
                if isinstance(ensured, dict):
                    main_session_entry = ensured.get("entry") or ensured
            except OpenClawGatewayError:
                main_session_entry = None
        return GatewaySessionsResponse(sessions=sessions_list, main_session=main_session_entry)

    async def get_session(
        self,
        *,
        session_id: str,
        board_id: UUID | None,
        organization_id: UUID,
        user: User | None,
    ) -> GatewaySessionResponse:
        params = GatewayResolveQuery(board_id=board_id)
        board, config, main_session = await self.resolve_gateway(params, user=user)
        self._require_same_org(board, organization_id)
        try:
            sessions_list = await self.list_sessions(config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        sessions_list = await self.with_main_session(
            sessions_list,
            config=config,
            main_session=main_session,
        )
        session_entry = next(
            (item for item in sessions_list if item.get("key") == session_id), None
        )
        if session_entry is None and main_session and session_id == main_session:
            try:
                ensured = await ensure_session(
                    main_session,
                    config=config,
                    label="Gateway Agent",
                )
                if isinstance(ensured, dict):
                    session_entry = ensured.get("entry") or ensured
            except OpenClawGatewayError:
                session_entry = None
        if session_entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        return GatewaySessionResponse(session=session_entry)

    async def get_session_history(
        self,
        *,
        session_id: str,
        board_id: UUID | None,
        organization_id: UUID,
        user: User | None,
    ) -> GatewaySessionHistoryResponse:
        board, config, _ = await self.require_gateway(board_id, user=user)
        self._require_same_org(board, organization_id)
        try:
            history = await get_chat_history(session_id, config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc
        if isinstance(history, dict) and isinstance(history.get("messages"), list):
            return GatewaySessionHistoryResponse(history=history["messages"])
        return GatewaySessionHistoryResponse(history=self.as_object_list(history))

    async def send_session_message(
        self,
        *,
        session_id: str,
        payload: GatewaySessionMessageRequest,
        board_id: UUID | None,
        organization_id: UUID,
        user: User | None,
    ) -> None:
        board, config, main_session = await self.require_gateway(board_id, user=user)
        self._require_same_org(board, organization_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        await require_board_access(self.session, user=user, board=board, write=True)
        try:
            if main_session and session_id == main_session:
                await ensure_session(main_session, config=config, label="Gateway Agent")
            await send_message(payload.content, session_key=session_id, config=config)
        except OpenClawGatewayError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc),
            ) from exc

    async def get_browser_status(
        self,
        *,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> BrowserStatusResponse:
        """Call browser.status on the connected gateway."""
        board, config, _ = await self.resolve_gateway(
            params, user=user, organization_id=organization_id
        )
        self._require_same_org(board, organization_id)
        try:
            result = await openclaw_call("browser.status", config=config)
            if isinstance(result, dict):
                raw_ctx = result.get("contexts", [])
                contexts = [
                    BrowserContextStatus(
                        provider=item.get("provider", ""),
                        healthy=bool(item.get("healthy")),
                        cdp_connected=bool(item.get("cdpConnected")),
                        last_checked_at=item.get("lastCheckedAt"),
                    )
                    for item in raw_ctx
                    if isinstance(item, dict)
                ]
                return BrowserStatusResponse(contexts=contexts)
            return BrowserStatusResponse(contexts=[])
        except OpenClawGatewayError as exc:
            return BrowserStatusResponse(
                contexts=[], error=normalize_gateway_error_message(str(exc))
            )

    async def get_channels_auth_status(
        self,
        *,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> ChannelsAuthStatusResponse:
        """Call channels.status and extract auth fields."""
        board, config, _ = await self.resolve_gateway(
            params, user=user, organization_id=organization_id
        )
        self._require_same_org(board, organization_id)
        try:
            result = await openclaw_call("channels.status", {"probe": False}, config=config)
            if not isinstance(result, dict):
                return ChannelsAuthStatusResponse(channels=[])
            channel_accounts = result.get("channelAccounts", {})
            if not isinstance(channel_accounts, dict):
                return ChannelsAuthStatusResponse(channels=[])
            channels: list[ChannelAuthStatus] = []
            for channel_id, accounts in channel_accounts.items():
                if not isinstance(accounts, list):
                    continue
                for acct in accounts:
                    if not isinstance(acct, dict):
                        continue
                    raw_pt = acct.get("providerType")
                    pt: Literal["web", "api"] = "web" if raw_pt == "web" else "api"
                    raw_expiry = acct.get("cookieExpiry")
                    expiry: int | None = int(raw_expiry) if isinstance(raw_expiry, (int, float)) else None
                    channels.append(
                        ChannelAuthStatus(
                            channel_id=channel_id,
                            auth_valid=bool(acct.get("authValid", True)),
                            needs_reauth=bool(acct.get("needsReauth", False)),
                            cookie_expiry=expiry,
                            provider_type=pt,
                        )
                    )
            return ChannelsAuthStatusResponse(channels=channels)
        except OpenClawGatewayError as exc:
            return ChannelsAuthStatusResponse(
                channels=[], error=normalize_gateway_error_message(str(exc))
            )

    async def reauth_channel(
        self,
        *,
        channel_id: str,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> ChannelReauthResponse:
        """Trigger reauthentication for a specific channel."""
        board, config, _ = await self.resolve_gateway(
            params, user=user, organization_id=organization_id
        )
        self._require_same_org(board, organization_id)
        try:
            result = await openclaw_call(
                "channels.reauth", {"channel": channel_id}, config=config
            )
            if isinstance(result, dict):
                return ChannelReauthResponse(
                    status=result.get("status", "error"),
                    auth_url=result.get("authUrl"),
                    channel_id=channel_id,
                    error=result.get("error"),
                )
            return ChannelReauthResponse(
                status="error",
                channel_id=channel_id,
                error="Unexpected response from gateway",
            )
        except OpenClawGatewayError as exc:
            return ChannelReauthResponse(
                status="error",
                channel_id=channel_id,
                error=normalize_gateway_error_message(str(exc)),
            )

    async def get_gateway_models(
        self,
        *,
        params: GatewayResolveQuery,
        organization_id: UUID,
        user: User | None,
    ) -> GatewayModelsResponse:
        """Call models.list and enrich with web model auth status."""
        from app.services.openclaw.web_model_utils import (
            is_web_model,
            provider_from_model_id,
        )

        board, config, _ = await self.resolve_gateway(
            params, user=user, organization_id=organization_id
        )
        self._require_same_org(board, organization_id)

        # Fetch models list
        try:
            result = await openclaw_call("models.list", config=config)
        except OpenClawGatewayError as exc:
            return GatewayModelsResponse(
                models=[], error=normalize_gateway_error_message(str(exc))
            )

        raw_models: list[object] = []
        if isinstance(result, dict):
            raw_models = self.as_object_list(result.get("models", []))

        # Fetch auth status for web providers (best-effort)
        auth_map: dict[str, bool] = {}
        try:
            auth_result = await openclaw_call(
                "channels.status", {"probe": False}, config=config
            )
            if isinstance(auth_result, dict):
                channel_accounts = auth_result.get("channelAccounts", {})
                if isinstance(channel_accounts, dict):
                    for ch_id, accounts in channel_accounts.items():
                        if isinstance(accounts, list) and accounts:
                            first = accounts[0]
                            if isinstance(first, dict):
                                auth_map[ch_id] = bool(first.get("authValid", True))
        except OpenClawGatewayError:
            pass

        models: list[GatewayModelItem] = []
        for item in raw_models:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue
            provider = item.get("provider", "")
            if not isinstance(provider, str):
                provider = ""
            web = is_web_model(model_id)
            provider_key = provider_from_model_id(model_id) if web else None
            auth_valid = auth_map.get(provider_key, True) if provider_key else True
            raw_ctx = item.get("contextWindow")
            ctx_window: int | None = (
                int(raw_ctx) if isinstance(raw_ctx, (int, float)) else None
            )
            models.append(
                GatewayModelItem(
                    id=model_id,
                    name=item.get("name", model_id)
                    if isinstance(item.get("name"), str)
                    else model_id,
                    provider=provider,
                    context_window=ctx_window,
                    provider_type="web" if web else "api",
                    auth_valid=auth_valid,
                    needs_reauth=not auth_valid,
                )
            )

        return GatewayModelsResponse(models=models)
