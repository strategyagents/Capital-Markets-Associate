"""Lightweight in-memory approval store for human-in-the-loop flows."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Dict, Literal, Optional

ApprovalStatus = Literal["pending", "approved", "denied", "error"]

_lock = threading.Lock()
_approvals: Dict[str, Dict[str, object]] = {}


def create_approval(agent: str, action: str, context: dict) -> str:
    token = str(uuid.uuid4())
    with _lock:
        _approvals[token] = {
            "status": "pending",
            "agent": agent,
            "action": action,
            "context": context,
            "updated_at": time.time(),
        }
    return token


def set_status(token: str, status: ApprovalStatus, meta: Optional[dict] = None) -> Dict[str, object]:
    with _lock:
        if token not in _approvals:
            _approvals[token] = {"status": status, "updated_at": time.time()}
        else:
            _approvals[token]["status"] = status
            _approvals[token]["updated_at"] = time.time()
            if meta:
                _approvals[token]["meta"] = meta
        return dict(_approvals[token], token=token)


def get_status(token: str) -> Dict[str, object]:
    with _lock:
        data = _approvals.get(token)
        if not data:
            return {"status": "unknown", "token": token}
        return dict(data, token=token)


def wait_for_status(token: str, timeout_seconds: int = 120, poll_interval: float = 2.0) -> Dict[str, object]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        status = get_status(token)
        if status.get("status") in {"approved", "denied", "error"}:
            return status
        time.sleep(poll_interval)
    return {"status": "timeout", "token": token}
