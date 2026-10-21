"""Gemini settings, read from the .env file every time they are needed.

The .env file is the single place to put the Gemini key and model:

    GEMINI_API_KEY=...
    GEMINI_MODEL=gemini-3.5-flash-lite

It is re-read on every request, so changing the model after a rate limit
only needs a save -- no backend restart. A value in .env wins over the same
variable exported in the shell. If .env has no value, the shell variable is
used, and if neither is set the model falls back to DEFAULT_MODEL.

TAARR_ENV_FILE can point to a different file (the test suite uses this so it
never reads a developer's real key).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

DEFAULT_MODEL = "gemini-2.5-flash-lite"
REPO_ROOT = Path(__file__).resolve().parents[2]


def env_file_path() -> Path | None:
    override = os.getenv("TAARR_ENV_FILE", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    for candidate in (Path.cwd() / ".env", REPO_ROOT / ".env"):
        if candidate.is_file():
            return candidate
    return None


def _setting(name: str) -> str:
    path = env_file_path()
    if path is not None:
        value = (dotenv_values(path).get(name) or "").strip()
        if value:
            return value
    return os.getenv(name, "").strip()


def gemini_api_key() -> str:
    return _setting("GEMINI_API_KEY")


def gemini_model() -> str:
    return _setting("GEMINI_MODEL") or DEFAULT_MODEL
