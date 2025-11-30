"""Portfolio management agent."""
from __future__ import annotations

import os

from google.adk.agents import Agent

from common.models import resolve_model
from common.sessions import configure_session_store
from common.telemetry import setup_telemetry
from common.tools import (
    calculate_portfolio_health,
    fetch_portfolio_positions,
    invoke_custom_mcp_tool,
)

AGENT_NAME = "portfolio"
os.environ.setdefault("AGENT_NAME", AGENT_NAME)
configure_session_store(AGENT_NAME)
setup_telemetry(AGENT_NAME)
MODEL = resolve_model()


root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL.identifier,
    description="Maintains holdings, allocations, and balance sheet level data.",
    instruction="""You control the canonical portfolio of records. Always verify holdings and
cash positions using the tools provided. When answering questions, include numerical
breakdowns, the timestamp of the data, and any assumptions (such as missing FX marks).
""",
    tools=[
        fetch_portfolio_positions,
        calculate_portfolio_health,
        invoke_custom_mcp_tool,
    ],
)
