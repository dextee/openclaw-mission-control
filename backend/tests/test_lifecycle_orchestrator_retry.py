# ruff: noqa: S101
"""FIX-17: transient gateway error retry in AgentLifecycleOrchestrator."""

from __future__ import annotations

from app.services.openclaw.gateway_rpc import OpenClawGatewayError
from app.services.openclaw.internal.retry import _is_transient_gateway_error
from app.services.openclaw.lifecycle_orchestrator import (
    _LIFECYCLE_RETRY_BASE_DELAY_S,
    _LIFECYCLE_RETRY_MAX_DELAY_S,
    _LIFECYCLE_RETRY_TIMEOUT_S,
)


def test_transient_marker_1012_service_restart() -> None:
    err = OpenClawGatewayError(
        "received 1012 (service restart) service restart; "
        "then sent 1012 (service restart) service restart"
    )
    assert _is_transient_gateway_error(err) is True


def test_transient_marker_connection_closed() -> None:
    assert _is_transient_gateway_error(OpenClawGatewayError("connection closed")) is True
    assert _is_transient_gateway_error(OpenClawGatewayError("connect call failed")) is True
    assert _is_transient_gateway_error(OpenClawGatewayError("Connection reset")) is True


def test_non_transient_errors_not_retried() -> None:
    assert _is_transient_gateway_error(OpenClawGatewayError("invalid request: bad uuid")) is False
    assert _is_transient_gateway_error(OpenClawGatewayError("agent not found")) is False
    # Non-OpenClawGatewayError should not be classified as transient.
    assert _is_transient_gateway_error(ValueError("network is unreachable")) is False


def test_lifecycle_retry_budget_is_short_enough_for_request_path() -> None:
    # If we ever crank these up, tests should remind us — long backoffs hurt
    # request latency and tie up DB locks (run_lifecycle holds SELECT FOR UPDATE).
    assert _LIFECYCLE_RETRY_TIMEOUT_S <= 60.0
    assert _LIFECYCLE_RETRY_BASE_DELAY_S < _LIFECYCLE_RETRY_MAX_DELAY_S
