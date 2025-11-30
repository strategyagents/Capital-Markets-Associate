"""Trader agent responsible for execution and human approvals."""
from __future__ import annotations

import os
from typing import Any, Dict

from google.adk.agents import Agent

from common.config import get_settings
from common.approvals import get_status as get_approval_status, wait_for_status
from common.models import resolve_model
from common.notifications import request_human_approval
from common.sessions import configure_session_store
from common.telemetry import log_agent_event, setup_telemetry
from common.mcp import MCPAuthorizationError
from common.tools import (
    fetch_open_orders,
    invoke_custom_mcp_tool,
    list_mcp_tools,
    request_trade_approval,
    submit_trade_order,
)

AGENT_NAME = "trader"
os.environ.setdefault("AGENT_NAME", AGENT_NAME)
configure_session_store(AGENT_NAME)
setup_telemetry(AGENT_NAME)
MODEL = resolve_model()


def _pin_agent_env() -> None:
    # Ensure shared modules read the correct agent name.
    os.environ["AGENT_NAME"] = AGENT_NAME


def execute_trade(symbol: str, side: str = "BUY", quantity: float | None = None, limit_price: float | None = None) -> dict:
    _pin_agent_env()
    paper_flag = os.getenv("TRADER_PAPER", "false").strip().lower() == "true"
    quantity_txt = f"{quantity}" if quantity is not None else ""
    summary = " ".join(
        part for part in [f"Execute {side}", quantity_txt, symbol, f"(entry={limit_price}, paper={paper_flag})"] if part
    )
    approval = request_trade_approval(
        summary=summary,
        order={
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "entry": limit_price,
            "paper": paper_flag,
        },
    )
    settings = get_settings()
    if settings.human_approval_required:
        status = approval.get("status")
        token = approval.get("token")
        if status in {"error", "denied"}:
            return {"approval": approval, "execution": {"error": "Trade halted: human approval failed"}}
        if status != "approved" and token:
            # Block briefly waiting for approval to flip.
            result = wait_for_status(token, timeout_seconds=settings.approval_wait_timeout_seconds, poll_interval=3.0)
            if result.get("status") == "approved":
                approval = result
            elif result.get("status") == "denied":
                return {"approval": result, "execution": {"error": "Trade denied by approver"}}
            elif result.get("status") == "timeout":
                return {"approval": result, "execution": {"status": "pending-approval", "error": "Timed out waiting for approval"}}
            else:
                return {"approval": result, "execution": {"status": "pending-approval"}}
    trade_result = submit_trade_order(symbol, side, quantity, limit_price)
    return {"approval": approval, "execution": trade_result}


def fetch_open_orders_with_approval() -> Dict[str, Any]:
    _pin_agent_env()
    request_human_approval(AGENT_NAME, "fetch-open-orders", {"note": "Trader requesting open orders"})
    return fetch_open_orders()


def invoke_custom_mcp_tool_with_approval(tool_name: str, **payload: Any) -> Dict[str, Any]:
    _pin_agent_env()
    # Generic approval gate before invoking arbitrary MCP tool.
    request_human_approval(AGENT_NAME, f"mcp:{tool_name}", {"payload": payload})
    return invoke_custom_mcp_tool(tool_name, **payload)


root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL.identifier,
    description="Executes approved trades and documents the lifecycle.",
    instruction="""You are the execution gatekeeper. Always request human approval before placing
orders, echo the parameters received, and capture fills in the trade journal.
When executing trades, confirm whether you are using paper or live based on the `paper` flag you send
and include that in your summary. When asked for open orders, call `fetch_open_orders` (it already uses paper=false)
and report the results without asking the user for additional parameters.
""",
    tools=[
        execute_trade,
        submit_trade_order,
        fetch_open_orders_with_approval,
        list_mcp_tools,
        invoke_custom_mcp_tool_with_approval,
    ],
)
