"""Centralized application settings loaded from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _to_list(raw: str | None) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    """Pydantic-powered settings model."""

    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    default_google_model: str = Field(default="gemini-2.0-flash-exp", alias="DEFAULT_GOOGLE_MODEL")
    model_provider: str = Field(default="gemini", alias="MODEL_PROVIDER")
    litellm_base_url: str = Field(default="http://localhost:4000", alias="LITELLM_BASE_URL")
    litellm_model: str = Field(default="ollama/gemma:2b", alias="LITELLM_MODEL")
    litellm_api_key: str = Field(default="", alias="LITELLM_API_KEY")

    graylog_endpoint: str = Field(default="10.20.80.15:4317", alias="GRAYLOG_OTLP_GRPC_ENDPOINT")
    graylog_insecure: bool = Field(default=True, alias="GRAYLOG_INSECURE")
    graylog_namespace: str = Field(default="agent-codex", alias="GRAYLOG_SERVICE_NAMESPACE")
    graylog_trace_sample_ratio: float = Field(default=1.0, alias="GRAYLOG_TRACE_SAMPLE_RATIO")

    mcp_server_url: str = Field(default="http://10.20.80.9:8085", alias="MCP_SERVER_URL")
    mcp_api_key: str = Field(default="", alias="MCP_API_KEY")
    mcp_request_timeout: int = Field(default=30, alias="MCP_REQUEST_TIMEOUT")

    orchestrator_mcp_tool_allowlist: str | None = Field(default=None, alias="ORCHESTRATOR_MCP_TOOL_ALLOWLIST")
    portfolio_mcp_tool_allowlist: str | None = Field(default=None, alias="PORTFOLIO_MCP_TOOL_ALLOWLIST")
    analytics_mcp_tool_allowlist: str | None = Field(default=None, alias="ANALYTICS_MCP_TOOL_ALLOWLIST")
    trader_mcp_tool_allowlist: str | None = Field(default=None, alias="TRADER_MCP_TOOL_ALLOWLIST")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    telegram_approver_username: str = Field(default="", alias="TELEGRAM_APPROVER_USERNAME")

    session_db_root: str = Field(default="data/sessions", alias="SESSION_DB_ROOT")
    fastapi_host: str = Field(default="0.0.0.0", alias="FASTAPI_HOST")
    fastapi_port: int = Field(default=8080, alias="FASTAPI_PORT")
    default_app_name: str = Field(default="agent-codex", alias="DEFAULT_AGENT_APP_NAME")
    human_approval_required: bool = Field(default=True, alias="HUMAN_APPROVAL_REQUIRED")
    approval_wait_timeout_seconds: int = Field(default=180, alias="APPROVAL_WAIT_TIMEOUT_SECONDS")

    orchestrator_url: str = Field(default="http://localhost:8080/agent-proxy/orchestrator", alias="ORCHESTRATOR_URL")
    portfolio_url: str = Field(default="http://localhost:8080/agent-proxy/portfolio", alias="PORTFOLIO_URL")
    analytics_url: str = Field(default="http://localhost:8080/agent-proxy/analytics", alias="ANALYTICS_URL")
    trader_url: str = Field(default="http://localhost:8080/agent-proxy/trader", alias="TRADER_URL")

    trader_webhook_url: str = Field(default="", alias="TRADER_WEBHOOK_URL")
    portfolio_data_source: str = Field(default="", alias="PORTFOLIO_DATA_SOURCE")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="allow")

    def allowed_tools(self, agent_name: str) -> List[str]:
        lookup: Dict[str, str | None] = {
            "orchestrator": self.orchestrator_mcp_tool_allowlist,
            "portfolio": self.portfolio_mcp_tool_allowlist,
            "analytics": self.analytics_mcp_tool_allowlist,
            "trader": self.trader_mcp_tool_allowlist,
        }
        raw_value = lookup.get(agent_name.lower())
        allowed = set(_to_list(raw_value))

        # Automatically permit tools that have explicit endpoint overrides via env vars.
        for key in os.environ:
            if key.startswith("MCP_TOOL_ENDPOINT_"):
                allowed.add(key.removeprefix("MCP_TOOL_ENDPOINT_"))

        return sorted(allowed)

    def tool_endpoint_override(self, tool_name: str) -> tuple[str, str] | None:
        env_key = f"MCP_TOOL_ENDPOINT_{tool_name}"
        value = os.getenv(env_key)
        if value and ":" in value:
            method, path = value.split(":", 1)
            return method.upper(), path

        bulk = os.getenv("MCP_TOOL_ENDPOINT_OVERRIDES")
        if bulk:
            for entry in bulk.split(","):
                if "=" not in entry:
                    continue
                name, spec = entry.split("=", 1)
                if name.strip() == tool_name and ":" in spec:
                    method, path = spec.split(":", 1)
                    return method.upper(), path
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
