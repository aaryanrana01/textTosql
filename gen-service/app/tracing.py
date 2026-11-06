"""Optional Langfuse tracing.

With credentials set, every request becomes a trace showing each pipeline step's timing and outcome,
and each LLM call's prompt, tokens and cost. Without them, everything in this module is a harmless no-op,
so tests, CI and local development never depend on an external service."""
import os

from .config import settings

ENABLED = bool(settings.langfuse_public_key and settings.langfuse_secret_key)

if ENABLED:
    # The SDK reads credentials from environment variables; settings loaded from .env aren't exported there.
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    os.environ.setdefault("LANGFUSE_BASE_URL", settings.langfuse_host)

    from langfuse import get_client, observe
    from langfuse.openai import AsyncOpenAI  # drop-in replacement: traces every LLM call automatically

    def update_current_span(**fields) -> None:
        get_client().update_current_span(**fields)

    def shutdown() -> None:
        get_client().shutdown()  # sends any buffered traces before the service stops

else:
    from openai import AsyncOpenAI  # noqa: F401

    def observe(func=None, **_options):
        """Do-nothing stand-in that supports both @observe and @observe(name=...)."""
        if callable(func):
            return func
        return lambda f: f

    def update_current_span(**_fields) -> None:
        return None

    def shutdown() -> None:
        return None