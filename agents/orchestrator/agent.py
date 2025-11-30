"""Orchestrator agent definition."""
from __future__ import annotations

import os
from typing import Any, Dict

import httpx
from google.adk.agents import Agent

from common.config import get_settings
from common.models import resolve_model
from common.sessions import configure_session_store
from common.telemetry import log_agent_event, setup_telemetry
from common.tools import (
    fetch_open_orders,
    fetch_quote_snapshot,
    invoke_custom_mcp_tool,
    list_agent_tools,
    list_mcp_tools,
)

SETTINGS = get_settings()
AGENT_NAME = "orchestrator"
os.environ.setdefault("AGENT_NAME", AGENT_NAME)
configure_session_store(AGENT_NAME)
setup_telemetry(AGENT_NAME)
MODEL = resolve_model()


def _run_child_agent(agent_name: str, agent_url: str, question: str) -> Dict[str, Any]:
    payload = {
        "appName": agent_name,
        "userId": AGENT_NAME,
        "sessionId": f"{AGENT_NAME}-{agent_name}",
        "newMessage": {
            "role": "user",
            "parts": [{"text": question}],
        },
    }
    log_agent_event(
        "agent.bridge.request",
        caller=AGENT_NAME,
        target=agent_name,
        payload=payload,
    )
    response = httpx.post(f"{agent_url}/run", json=payload, timeout=45)
    response.raise_for_status()
    data = response.json()
    log_agent_event(
        "agent.bridge.response",
        caller=AGENT_NAME,
        target=agent_name,
        response=data,
    )
    return data


def consult_portfolio(question: str) -> Dict[str, Any]:
    return _run_child_agent("portfolio", SETTINGS.portfolio_url, question)


def consult_analytics(question: str) -> Dict[str, Any]:
    return _run_child_agent("analytics", SETTINGS.analytics_url, question)


def instruct_trader(instruction: str) -> Dict[str, Any]:
    return _run_child_agent("trader", SETTINGS.trader_url, instruction)


root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL.identifier,
    description="Coordinates all downstream agents and enforces governance.",
    instruction="""You are the orchestrator for the trading collective. Triage each user request,
decide which specialist to engage, and summarize their responses. When trade execution
is required, gather analytics context, validate portfolio constraints, and request
human approval from the trader agent before final execution. Route order/execution
questions to the trader, portfolio questions to the portfolio agent, and quote
requests to analytics (or use `fetch_quote_snapshot` directly). Use
`list_agent_tools`/`list_mcp_tools` to discover capabilities; prefer automatic
delegation without asking the user for MCP parameters. Prefer cite-style summaries
that capture which agent supplied which fact.
""",
    tools=[
        consult_portfolio,
        consult_analytics,
        instruct_trader,
        invoke_custom_mcp_tool,
        list_mcp_tools,
        fetch_open_orders,
        list_agent_tools,
        fetch_quote_snapshot,
    ],
)
