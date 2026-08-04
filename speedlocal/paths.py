from __future__ import annotations

import os
from pathlib import Path


V2_SOURCE_ROOT_ENV = "SPEEDLOCAL_V2_SOURCE_ROOT"
GENERATED_RUNTIME_ROOT_ENV = "SPEEDLOCAL_GENERATED_ROOT"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def provider_root(provider: str) -> Path:
    if provider == "repo":
        return repo_root()
    if provider == "v2_archive":
        configured = os.environ.get(V2_SOURCE_ROOT_ENV, "").strip()
        if not configured:
            raise FileNotFoundError(f"{V2_SOURCE_ROOT_ENV} is not configured")
        root = Path(configured).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f"V2 source root does not exist: {root}")
        return root
    if provider == "generated_runtime":
        configured = os.environ.get(GENERATED_RUNTIME_ROOT_ENV, "").strip()
        if not configured:
            raise FileNotFoundError(
                f"{GENERATED_RUNTIME_ROOT_ENV} is not configured"
            )
        root = Path(configured).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(
                f"Generated runtime root does not exist: {root}"
            )
        return root
    raise ValueError(f"Unsupported source provider: {provider}")


def resolve_source_path(provider: str, path_value: str) -> Path:
    root = provider_root(provider).resolve()
    candidate = Path(path_value)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not _within(root, resolved):
        raise ValueError(f"Source path escapes provider root: {path_value}")
    return resolved
