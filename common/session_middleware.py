"""Middleware that ensures ADK sessions exist before hitting /run."""
from __future__ import annotations

import inspect
import json
from typing import Any, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.concurrency import iterate_in_threadpool

from .telemetry import log_agent_event, record_model_payload


async def _call_session_method(session_service: Any, primary: str, fallback: Optional[str] = None, **kwargs: Any):
    for method_name in filter(None, [primary, fallback]):
        method = getattr(session_service, method_name, None)
        if not method:
            continue
        result = method(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
    raise AttributeError(f"Session service missing {primary}/{fallback}")


class AutoCreateSessionMiddleware(BaseHTTPMiddleware):
    """Adds automatic session creation for ADK /run requests."""

    def __init__(self, app, session_service: Any, default_app_name: str):
        super().__init__(app)
        self.session_service = session_service
        self.default_app_name = default_app_name

    async def dispatch(self, request: Request, call_next):
        log_context: tuple[str, bool] | None = None
        # When agent apps are mounted under a prefix (for example /agents/<name>/run),
        # request.url.path carries the prefixed path. Use suffix matching so the
        # middleware still triggers.
        if request.method == "POST" and request.url.path.endswith("/run"):
            service = getattr(request.app.state, "session_service", None) or self.session_service
            if service:
                body_bytes = await request.body()
                try:
                    data = json.loads(body_bytes or b"{}")
                except json.JSONDecodeError:
                    data = {}

                app_name = data.get("appName") or self.default_app_name
                data["appName"] = app_name
                user_id = data.get("userId")
                session_id = data.get("sessionId")
                record_model_payload(app_name, "request", data)
                log_context = (app_name, True)

                if user_id and session_id:
                    session = await _call_session_method(
                        service,
                        primary="get_session",
                        fallback="get_session_sync",
                        app_name=app_name,
                        user_id=user_id,
                        session_id=session_id,
                    )
                    if session is None:
                        await _call_session_method(
                            service,
                            primary="create_session",
                            fallback="create_session_sync",
                            app_name=app_name,
                            user_id=user_id,
                            session_id=session_id,
                            state={},
                        )
                        log_agent_event(
                            "session.auto_created",
                            agent_name=app_name,
                            user_id=user_id,
                            session_id=session_id,
                        )

                new_body = json.dumps(data).encode("utf-8")

                async def receive():
                    return {"type": "http.request", "body": new_body}

                request._receive = receive
        response = await call_next(request)

        if log_context:
            agent_name, _ = log_context
            body = b""
            if response.body_iterator is not None:
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                body = b"".join(chunks)
                response.body_iterator = iterate_in_threadpool(iter(chunks))
            else:
                body = getattr(response, "body", b"") or b""
            try:
                payload = json.loads(body)
            except Exception:
                payload = body.decode("utf-8", errors="ignore")
            record_model_payload(agent_name, "response", payload)

        return response
