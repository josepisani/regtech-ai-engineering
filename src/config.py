"""Central config: read everything from the environment, fail loudly if missing.

Keeping config in one place (and out of the code) is the habit that keeps
secrets uncommitted and makes the app portable from your laptop to Cloud Run.
"""
from __future__ import annotations

import os
from typing import overload
from dotenv import load_dotenv

# Load .env into the environment if present (a no-op in production, where real
# env vars are set by Cloud Run / Secret Manager instead of a file).
load_dotenv()


def require(name: str) -> str:
    """Return an env var, or raise a clear error telling you what to set."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


# Two overloads so the type checker knows what callers know: with a default,
# this can never return None. Without one, it can. Callers see only these.
@overload
def optional(name: str) -> str | None: ...
@overload
def optional(name: str, default: str) -> str: ...


def optional(name: str, default: str | None = None) -> str | None:
    return os.getenv(name) or default


# Anthropic
ANTHROPIC_API_KEY = optional("ANTHROPIC_API_KEY")
CLAUDE_MODEL = optional("CLAUDE_MODEL", "claude-sonnet-5")
MAX_TOKENS = int(optional("MAX_TOKENS", "1024"))

# Google Cloud
GOOGLE_CLOUD_PROJECT = optional("GOOGLE_CLOUD_PROJECT")
GEMINI_API_KEY = optional("GEMINI_API_KEY")
