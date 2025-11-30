"""Shared tool implementations consumed by the agents."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx

from .config import get_settings
from .mcp import MCPAuthorizationError, get_mcp_client
from .notifications import request_human_approval
from .telemetry import log_agent_event


def _agent_name() -> str:
    return os.getenv("AGENT_NAME", "agent")


def fetch_portfolio_positions(portfolio_id: str = "default", symbol: Optional[str] = None, paper: bool = True) -> Dict[str, Any]:
    client = get_mcp_client(_agent_name())
    payload: Dict[str, Any] = {"paper": paper}
    # Some backends may accept additional filters; include symbol only if provided.
    if symbol is not None:
        payload["symbol"] = symbol
    result = client.invoke("get_positions", payload)
    log_agent_event("tool.fetch_portfolio_positions", payload=payload, response=result)
    return result


def fetch_open_orders() -> Dict[str, Any]:
    """Retrieve open orders from MCP."""
    client = get_mcp_client(_agent_name())
    tool_name = "get_open_orders_order_open_get"
    payload = {"paper": False}
    result = client.invoke(tool_name, payload)
    log_agent_event("tool.get_open_orders_order_open_get", tool=tool_name, payload=payload, response=result)
    return result


def list_mcp_tools() -> Dict[str, Any]:
    """Fetch the MCP server's advertised endpoints for quick discovery."""
    settings = get_settings()
    url = f"{settings.mcp_server_url.rstrip('/')}/endpoints"
    headers: Dict[str, str] = {}
    if settings.mcp_api_key:
        headers["Authorization"] = f"Bearer {settings.mcp_api_key}"

    try:
        response = httpx.get(url, headers=headers, timeout=settings.mcp_request_timeout)
        response.raise_for_status()
        try:
            data = response.json()
        except Exception:
            data = response.text
        log_agent_event("tool.list_mcp_tools", url=url, status=response.status_code)
        return {"url": url, "status": response.status_code, "endpoints": data}
    except Exception as exc:  # noqa: BLE001
        log_agent_event("tool.list_mcp_tools.failed", url=url, error=str(exc))
        return {"error": str(exc), "url": url}


def list_agent_tools(agent_name: str | None = None) -> Dict[str, Any]:
    """List MCP tools configured for an agent based on allowlists and env overrides."""
    settings = get_settings()
    target = agent_name or _agent_name()

    allowlisted = set(settings.allowed_tools(target))
    override_tools = {
        key.removeprefix("MCP_TOOL_ENDPOINT_").lower()
        for key in os.environ
        if key.startswith("MCP_TOOL_ENDPOINT_")
    }
    tools = sorted(allowlisted.union(override_tools))
    return {"agent": target, "tools": tools}


def calculate_portfolio_health(metric: str = "allocation") -> Dict[str, Any]:
    client = get_mcp_client(_agent_name())
    payload = {"metric": metric}
    result = client.invoke("calculate_portfolio_health", payload)
    log_agent_event("tool.calculate_portfolio_health", payload=payload, response=result)
    return result


def generate_market_insight(topic: str, timeframe: str = "1d") -> Dict[str, Any]:
    client = get_mcp_client(_agent_name())
    payload = {"topic": topic, "timeframe": timeframe}
    result = client.invoke("technical_analysis", payload)
    log_agent_event("tool.generate_market_insight", payload=payload, response=result)
    return result


def fetch_quote_snapshot(symbol: str) -> Dict[str, Any]:
    """Retrieve a real-time quote snapshot for a symbol."""
    client = get_mcp_client(_agent_name())
    # MCP expects `symbols` and `paper` query params.
    payload = {"symbols": symbol, "paper": False}
    result = client.invoke("get_quoteSnapshot_marketdata_quote_snapshot_get", payload)
    log_agent_event("tool.fetch_quote_snapshot", payload=payload, response=result)
    return result


def submit_trade_order(symbol: str, side: str | None = "BUY", quantity: float | None = None, limit_price: float | None = None) -> Dict[str, Any]:
    client = get_mcp_client(_agent_name())
    # Default to paper trading unless explicitly overridden via env.
    paper_flag = os.getenv("TRADER_PAPER", "false").strip().lower() == "true"

    # The MCP endpoint only needs sym/entry/paper; side/quantity are kept for logging/compliance but are not sent.
    mcp_payload = {
        "sym": symbol,
        "entry": "" if limit_price is None else limit_price,
        "paper": str(paper_flag).lower(),
    }
    log_payload = {
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "entry": limit_price,
        "paper": paper_flag,
    }
    result = client.invoke("execute_trade", mcp_payload)
    log_agent_event("tool.submit_trade_order", payload=log_payload, response=result)
    return result


def record_trade_journal(entry: Dict[str, Any]) -> Dict[str, Any]:
    client = get_mcp_client(_agent_name())
    result = client.invoke("record_trade_journal", entry)
    log_agent_event("tool.record_trade_journal", payload=entry, response=result)
    return result


def request_trade_approval(summary: str, order: Dict[str, Any]) -> Dict[str, Any]:
    context = {"summary": summary, "order": order}
    approval = request_human_approval(_agent_name(), "trade-approval", context)
    log_agent_event("tool.request_trade_approval", payload=context, response=approval)
    return approval


def invoke_custom_mcp_tool(tool_name: str, **payload: Any) -> Dict[str, Any]:
    client = get_mcp_client(_agent_name())
    try:
        result = client.invoke(tool_name, payload)
        log_agent_event("tool.invoke_custom_mcp_tool", tool=tool_name, payload=payload, response=result)
        return result
    except MCPAuthorizationError as exc:
        log_agent_event("tool.invoke_custom_mcp_tool.blocked", tool=tool_name, payload=payload, error=str(exc))
        raise
