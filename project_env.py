from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_project_env() -> None:
    root = Path(__file__).resolve().parent
    # Keep shell-exported values authoritative while allowing local-only
    # overrides to win over a shared `.env` file when both exist.
    load_dotenv(root / ".env.local", override=False)
    load_dotenv(root / ".env", override=False)
