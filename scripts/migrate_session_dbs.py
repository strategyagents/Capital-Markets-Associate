"""Migrate or reset legacy ADK SQLite session files to the latest schema.

Running this script backs up each ``*.db`` file in the session directory to
``<name>.db.bak`` and replaces it with the migrated copy produced by the ADK
migration helper. If the helper is unavailable, the script archives the old
database so a fresh schema can be created on the next start. Use it after
upgrading ``google-adk`` when startup fails with an "old schema" error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

MIGRATION_MODULE = "google.adk.sessions.migrate_from_sqlalchemy_sqlite"
DEFAULT_SESSION_ROOT = Path(__file__).resolve().parent.parent / "data" / "sessions"


def discover_databases(session_root: Path) -> List[Path]:
    """Return sorted SQLite database paths under the provided directory."""
    if not session_root.exists():
        return []
    return sorted(db for db in session_root.glob("*.db") if db.is_file())


def archive_database(db_path: Path) -> Path:
    """Move the existing database aside so a fresh schema can be created."""
    backup_path = db_path.with_suffix(".db.bak")
    if backup_path.exists():
        backup_path.unlink()
    db_path.rename(backup_path)
    return backup_path


def migrate_database(db_path: Path) -> bool:
    """Migrate a single database file; returns True on success.

    Side effects:
    - Creates ``<name>.db.new`` during migration.
    - Replaces the original file with the migrated copy.
    - Writes a backup to ``<name>.db.bak``.
    """
    temp_path = db_path.with_suffix(".db.new")
    backup_path = db_path.with_suffix(".db.bak")

    if temp_path.exists():
        temp_path.unlink()

    cmd = [
        sys.executable,
        "-m",
        MIGRATION_MODULE,
        "--source_db_path",
        str(db_path),
        "--dest_db_path",
        str(temp_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        reason = result.stderr.strip() or result.stdout.strip() or "unknown error"
        if MIGRATION_MODULE in reason or "No module named" in reason:
            backup_path = archive_database(db_path)
            print(
                f"Archived {db_path.name} to {backup_path.name}; migration helper missing "
                "so a fresh schema will be created on next startup"
            )
            return True

        print(f"Skipping {db_path.name}: {reason}")
        if temp_path.exists():
            temp_path.unlink()
        return False

    backup_path = archive_database(db_path)
    temp_path.rename(db_path)
    print(f"Migrated {db_path.name} (backup saved to {backup_path.name})")
    return True


def migrate_all(session_root: Path) -> int:
    """Migrate all databases beneath the session root; returns failure count."""
    databases = discover_databases(session_root)
    if not databases:
        print(f"No SQLite session files found under {session_root}")
        return 0

    failures = 0
    for db_path in databases:
        if not migrate_database(db_path):
            failures += 1
    print(f"{len(databases) - failures}/{len(databases)} databases migrated")
    return failures


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for migration options."""
    parser = argparse.ArgumentParser(description="Upgrade ADK session SQLite schemas.")
    parser.add_argument(
        "--session-root",
        type=Path,
        default=DEFAULT_SESSION_ROOT,
        help="Directory containing *.db session files (default: data/sessions)",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> None:
    """CLI entrypoint."""
    args = parse_args(argv)
    failures = migrate_all(args.session_root)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
