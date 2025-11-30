"""Analytics and research agent."""
from __future__ import annotations

import os

from google.adk.agents import Agent

from common.models import resolve_model
from common.sessions import configure_session_store
from common.telemetry import setup_telemetry
from common.tools import fetch_quote_snapshot, generate_market_insight, invoke_custom_mcp_tool

AGENT_NAME = "analytics"
os.environ.setdefault("AGENT_NAME", AGENT_NAME)
configure_session_store(AGENT_NAME)
setup_telemetry(AGENT_NAME)
MODEL = resolve_model()


root_agent = Agent(
    name=AGENT_NAME,
    model=MODEL.identifier,
    description="Produces technical and fundamental analytics to aid the trading workflow.",
    instruction="""Produce structured analyses for any requested asset or theme. When providing
recommendations, cite at least two signals (e.g., price action, macro catalysts,
sentiment). Include uncertainty levels and suggest what additional data would change
your view.
""",
    tools=[
        generate_market_insight,
        fetch_quote_snapshot,
        invoke_custom_mcp_tool,
    ],
)
