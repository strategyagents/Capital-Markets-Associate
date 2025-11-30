"""Notification utilities for human-in-the-loop workflows."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

from .config import get_settings
from .approvals import create_approval, set_status
from .telemetry import log_agent_event


def send_telegram_message(
    message: str,
    parse_mode: str | None = None,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log_agent_event("notification.telegram.skipped", reason="missing-config")
        return {"status": "skipped"}

    payload: Dict[str, Any] = {
        "chat_id": settings.telegram_chat_id,
        "text": message,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        response = httpx.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        log_agent_event("notification.telegram.sent", response=data)
        return {"status": "sent", "response": data}
    except Exception as exc:  # noqa: BLE001
        log_agent_event("notification.telegram.error", error=str(exc))
        return {"status": "error", "error": str(exc)}


def request_human_approval(agent_name: str, action: str, context: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_settings()
    if not settings.human_approval_required:
        log_agent_event("human.approval.auto", agent=agent_name, action=action)
        return {"status": "auto-approved"}

    token = create_approval(agent_name, action, context)
    pretty_context = json.dumps({"token": token, **context}, indent=2)
    approver = settings.telegram_approver_username or "human"
    base_url = getattr(settings, "approval_webhook_base_url", "") or f"http://{settings.fastapi_host}:{settings.fastapi_port}"
    approve_url = f"{base_url}/webhook/approval?token={token}&status=approved"
    deny_url = f"{base_url}/webhook/approval?token={token}&status=denied"

    header = f"[{agent_name}] requests approval for `{action}` from @{approver}\nToken: `{token}`\n"
    message = header + "Context:\n```\n" + pretty_context + "\n```"
    markup: Dict[str, Any] = {
        "inline_keyboard": [
            [{"text": "Approve", "url": approve_url}, {"text": "Deny", "url": deny_url}],
        ]
    }
    result = send_telegram_message(message, parse_mode="Markdown", reply_markup=markup)
    if result.get("status") == "error":
        set_status(token, "error", {"error": result.get("error", "approval notification failed")})
        return {"status": "error", "error": result.get("error", "approval notification failed"), "token": token}

    return {"status": "pending", "token": token, "detail": result}
