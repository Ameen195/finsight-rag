"""Langfuse tracing. Without keys the client is created with tracing disabled, so `@observe`
becomes a no-op and the app runs unchanged."""

from contextlib import AbstractContextManager, nullcontext
from functools import lru_cache

from langfuse import Langfuse, get_client, observe

from finsight.config import get_settings

__all__ = ["init_tracing", "current_trace_id", "flush", "observe"]


@lru_cache(maxsize=1)
def init_tracing() -> bool:
    """Create the process-wide Langfuse client once; True if traces are being sent."""
    s = get_settings()
    enabled = bool(s.langfuse_public_key and s.langfuse_secret_key)
    Langfuse(
        public_key=s.langfuse_public_key or "",
        secret_key=s.langfuse_secret_key or "",
        host=s.langfuse_host,
        tracing_enabled=enabled,
    )
    return enabled


def root_span(name: str) -> AbstractContextManager:
    """Context manager that opens a root trace span (a no-op when tracing is off).

    Needed for generators, which `@observe` cannot wrap across their whole lifetime.
    """
    return get_client().start_as_current_observation(name=name) if init_tracing() else nullcontext()


def current_trace_id() -> str | None:
    """Trace id of the observed call in progress, or None when tracing is off."""
    return get_client().get_current_trace_id() if init_tracing() else None


def flush() -> None:
    """Send buffered traces (call before a short-lived process exits)."""
    if init_tracing():
        get_client().flush()
