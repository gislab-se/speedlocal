from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .catalog import resolve_repo_path


@dataclass(frozen=True)
class BackendStatus:
    backend: str
    available: bool
    message: str


def postgres_status() -> BackendStatus:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return BackendStatus("postgres", False, "DATABASE_URL is not set.")
    try:
        import psycopg  # type: ignore
    except Exception:
        return BackendStatus("postgres", False, "psycopg is not installed.")
    try:
        with psycopg.connect(url, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()
    except Exception as exc:
        return BackendStatus("postgres", False, f"Postgres unavailable: {exc}")
    return BackendStatus("postgres", True, "Postgres connection succeeded.")


def file_fallback_rows(region: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = region.get("runtime") or {}
    rows: list[dict[str, Any]] = []
    for item in runtime.get("file_fallbacks") or []:
        if not isinstance(item, dict):
            continue
        path_value = str(item.get("path") or "")
        resolved = resolve_repo_path(path_value)
        rows.append(
            {
                "id": item.get("id", ""),
                "kind": item.get("kind", ""),
                "required_for_full_runtime": bool(item.get("required_for_full_runtime")),
                "path": path_value,
                "exists": bool(resolved and Path(resolved).exists()),
                "source": item.get("source", ""),
            }
        )
    return rows


def selected_backend(region: dict[str, Any]) -> BackendStatus:
    status = postgres_status()
    if status.available:
        return status
    fallback_count = len(file_fallback_rows(region))
    if fallback_count:
        return BackendStatus(
            "file_fallback",
            True,
            f"Using documented file fallback contract ({fallback_count} entries). Source availability is checked below.",
        )
    return BackendStatus("unavailable", False, "No Postgres connection or file fallbacks.")
