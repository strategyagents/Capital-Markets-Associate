"""Session persistence helpers backed by SQLite files."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from google.adk.sessions import DatabaseSessionService, InMemorySessionService

from .config import get_settings

log = logging.getLogger(__name__)


def session_db_path(agent_name: str) -> Path:
    root = Path(get_settings().session_db_root)
    root.mkdir(parents=True, exist_ok=True)
    return (root / f"{agent_name}.db").resolve()


def session_db_url(agent_name: str) -> str:
    return f"sqlite:///{session_db_path(agent_name)}"


def configure_session_store(agent_name: str, update_env: bool = True) -> str:
    url = session_db_url(agent_name)
    if update_env:
        os.environ["SESSION_DB_URL"] = url
    return url


def create_session_service(agent_name: str, session_db_url: str) -> Any:
    try:
        service = DatabaseSessionService(db_url=session_db_url)
        log.info("Using database session store", extra={"agent": agent_name, "url": session_db_url})
        return service
    except Exception as exc:  # noqa: BLE001
        log.warning("Falling back to in-memory sessions", extra={"agent": agent_name, "error": str(exc)})
        return InMemorySessionService()
