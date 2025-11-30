"""FastAPI entrypoint hosting all agents and an orchestration proxy."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from google.adk.cli.fast_api import get_fast_api_app
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from fastapi.responses import JSONResponse
from fastapi import Query

from common.config import get_settings
from common.session_middleware import AutoCreateSessionMiddleware
from common.sessions import configure_session_store, create_session_service
from common.telemetry import log_agent_event, setup_telemetry
from common.approvals import set_status, get_status

BASE_DIR = Path(__file__).resolve().parent.parent
AGENT_NAMES = ["orchestrator", "portfolio", "analytics", "trader"]
AGENTS_ROOT = BASE_DIR / "agents"
SETTINGS = get_settings()
setup_telemetry("agent-platform")


class RunRequest(BaseModel):
    text: str
    session_id: str
    user_id: str = "api-user"
    agent: str = "orchestrator"


def _build_agent_payload(request: RunRequest) -> Dict[str, object]:
    return {
        "appName": request.agent,
        "userId": request.user_id,
        "sessionId": request.session_id,
        "newMessage": {
            "role": "user",
            "parts": [{"text": request.text}],
        },
    }


async def _ensure_session(agent_app: FastAPI, agent_name: str, user_id: str | None, session_id: str | None) -> None:
    """Create the session if it doesn't already exist for the target agent."""
    if not user_id or not session_id:
        return

    transport = ASGITransport(app=agent_app)
    async with AsyncClient(transport=transport, base_url=f"http://{agent_name}.local") as client:
        existing = await client.get(f"/apps/{agent_name}/users/{user_id}/sessions/{session_id}")
        if existing.status_code == 200:
            return

        created = await client.post(
            f"/apps/{agent_name}/users/{user_id}/sessions/{session_id}",
            json={},
        )
        if created.status_code >= 400:
            log_agent_event(
                "session.auto_create.failed",
                agent_name=agent_name,
                user_id=user_id,
                session_id=session_id,
                status=created.status_code,
                detail=created.text,
            )
            return
        log_agent_event(
            "session.auto_created",
            agent_name=agent_name,
            user_id=user_id,
            session_id=session_id,
            source="fastapi.orchestrate",
        )


app = FastAPI(title="Agent Codex", version="0.1.0")


def _mount_agents() -> Dict[str, FastAPI]:
    registry: Dict[str, FastAPI] = {}
    for name in AGENT_NAMES:
        agent_dir = AGENTS_ROOT / name
        if not agent_dir.exists():
            raise RuntimeError(f"Missing agent directory: {agent_dir}")
        session_uri = configure_session_store(name, update_env=False)
        session_service = create_session_service(name, session_uri)
        agent_app = get_fast_api_app(
            agents_dir=str(AGENTS_ROOT),
            session_service_uri=session_uri,
            web=False,
            host=SETTINGS.fastapi_host,
            port=SETTINGS.fastapi_port,
        )
        mount_path = f"/agents/{name}"
        agent_app.state.session_service = session_service
        agent_app.add_middleware(
            AutoCreateSessionMiddleware,
            session_service=session_service,
            default_app_name=name,
        )
        app.mount(mount_path, agent_app)
        registry[name] = agent_app
    return registry


AGENT_APPS = _mount_agents()


@app.get("/health", tags=["infra"])
async def health() -> Dict[str, object]:
    return {
        "status": "ok",
        "agents": list(AGENT_APPS.keys()),
        "model_provider": SETTINGS.model_provider,
    }


@app.post("/orchestrate", tags=["agents"])
async def orchestrate(request: RunRequest) -> Any:
    agent_name = request.agent or "orchestrator"
    orchestrator_app = AGENT_APPS.get(agent_name)
    if not orchestrator_app:
        raise HTTPException(status_code=500, detail=f"Agent {agent_name} not mounted")

    await _ensure_session(orchestrator_app, agent_name, request.user_id, request.session_id)

    payload = _build_agent_payload(request)
    log_agent_event("api.orchestrate.request", payload=payload)
    transport = ASGITransport(app=orchestrator_app)
    async with AsyncClient(transport=transport, base_url="http://orchestrator.local") as client:
        response = await client.post("/run", json=payload)
    if response.status_code >= 400:
        log_agent_event("api.orchestrate.error", status=response.status_code, text=response.text)
        raise HTTPException(status_code=response.status_code, detail=response.text)
    result = response.json()
    log_agent_event("api.orchestrate.response", response=result)
    return result


@app.post("/agent-proxy/{agent}/run", tags=["agents"])
async def proxy_agent(agent: str, request: Request) -> JSONResponse:
    target = AGENT_APPS.get(agent)
    if not target:
        raise HTTPException(status_code=404, detail=f"Agent {agent} not mounted")

    payload = await request.json()
    payload = dict(payload or {})
    payload.setdefault("appName", agent)
    await _ensure_session(target, payload["appName"], payload.get("userId"), payload.get("sessionId"))
    transport = ASGITransport(app=target)
    async with AsyncClient(transport=transport, base_url=f"http://{agent}.local") as client:
        response = await client.post("/run", json=payload)
    log_agent_event("api.agent_proxy", agent=agent, status=response.status_code)
    return JSONResponse(status_code=response.status_code, content=response.json())


@app.get("/webhook/approval", tags=["approvals"])
async def approval_webhook(token: str = Query(...), status: str = Query(...)) -> Dict[str, object]:
    status_normalized = status.lower()
    if status_normalized not in {"approved", "denied"}:
        raise HTTPException(status_code=400, detail="status must be approved or denied")
    record = set_status(token, status_normalized)  # type: ignore[arg-type]
    log_agent_event("approval.webhook.received", token=token, status=status_normalized)
    return {"ok": True, "token": token, "status": status_normalized, "record": record}
