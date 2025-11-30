"""Utility client for interacting with the MCP server with per-agent allowlists."""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List

import httpx
from httpx import HTTPStatusError, RequestError
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from .config import get_settings
from .telemetry import record_tool_invocation


class MCPAuthorizationError(RuntimeError):
    """Raised when an agent invokes a tool outside its allowlist."""


class MCPClient:
    def __init__(self, agent_name: str, allowed_tools: List[str]):
        self.agent_name = agent_name
        # Always enforce the configured allowlist; an empty list means no tools are permitted.
        self.allowed_tools = {tool for tool in allowed_tools} if allowed_tools is not None else None
        self._settings = get_settings()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), reraise=True)
    def _request(self, method: str, url: str, payload: Dict[str, Any], headers: Dict[str, str]) -> httpx.Response:
        return httpx.request(method, url, json=payload if method != "GET" else None, params=payload if method == "GET" else None, headers=headers, timeout=self._settings.mcp_request_timeout)

    def invoke(self, tool_name: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if self.allowed_tools is not None and tool_name not in self.allowed_tools:
            record_tool_invocation(self.agent_name, tool_name, "blocked", reason="not-allowed")
            raise MCPAuthorizationError(f"{self.agent_name} cannot invoke {tool_name}")

        request_payload = payload or {}
        headers: Dict[str, str] = {}
        if self._settings.mcp_api_key:
            headers["Authorization"] = f"Bearer {self._settings.mcp_api_key}"

        override = self._settings.tool_endpoint_override(tool_name)
        if override:
            method, path = override
            expanded_path = path
            for key, value in request_payload.items():
                placeholder = f"{{{key}}}"
                if placeholder in expanded_path:
                    expanded_path = expanded_path.replace(placeholder, str(value))
            base = self._settings.mcp_server_url.rstrip('/')
            url = f"{base}{expanded_path}"
        else:
            method = "POST"
            url = f"{self._settings.mcp_server_url.rstrip('/')}/tools/{tool_name}"
        record_tool_invocation(self.agent_name, tool_name, "requested", payload=request_payload)
        try:
            response = self._request(method, url, request_payload, headers)
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                # Some MCP servers return Python-style literals; fall back to literal_eval.
                import ast  # Local import to avoid global overhead.

                try:
                    data = ast.literal_eval(response.text)
                except Exception:
                    data = {"raw": response.text}
            record_tool_invocation(self.agent_name, tool_name, "succeeded", response=data)
            return data
        except HTTPStatusError as exc:
            record_tool_invocation(
                self.agent_name,
                tool_name,
                "failed",
                status_code=exc.response.status_code,
                error=exc.response.text,
            )
            return {
                "error": f"MCP tool {tool_name} failed with status {exc.response.status_code}",
                "detail": exc.response.text,
            }
        except RetryError as exc:
            root = exc.last_attempt.exception()
            record_tool_invocation(self.agent_name, tool_name, "failed", error=str(root))
            return {
                "error": f"MCP tool {tool_name} request error",
                "detail": str(root),
            }
        except RequestError as exc:
            record_tool_invocation(self.agent_name, tool_name, "failed", error=str(exc))
            return {
                "error": f"MCP tool {tool_name} request error",
                "detail": str(exc),
            }
        except Exception as exc:  # noqa: BLE001
            record_tool_invocation(self.agent_name, tool_name, "failed", error=str(exc))
            return {
                "error": f"MCP tool {tool_name} unexpected error",
                "detail": str(exc),
            }


@lru_cache(maxsize=4)
def get_mcp_client(agent_name: str) -> MCPClient:
    settings = get_settings()
    return MCPClient(agent_name=agent_name, allowed_tools=settings.allowed_tools(agent_name))
