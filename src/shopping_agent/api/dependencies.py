"""FastAPI dependencies: build once at app startup, inject per request.

This is the central wiring point — editing here is how you swap a
gateway or sink without touching route code."""

from __future__ import annotations

from functools import lru_cache

from shopping_agent.config import AppConfig, load_config, verify_secrets
from shopping_agent.conversation.state import SessionStore
from shopping_agent.debug.trace import DebugTraceBuffer, init_trace_buffer
from shopping_agent.events.bus import EventBus, build_bus
from shopping_agent.gateway.role1_omni import Role1OmniAdapter


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    cfg = load_config()
    verify_secrets(cfg)
    # Initialize the debug trace buffer here so the Role 1 adapter's
    # (lazy) call to get_trace_buffer() picks up an enabled instance
    # before the first request lands.
    init_trace_buffer(cfg.debug)
    return cfg


@lru_cache(maxsize=1)
def get_event_bus() -> EventBus:
    return build_bus(get_config().events)


@lru_cache(maxsize=1)
def get_role1() -> Role1OmniAdapter:
    return Role1OmniAdapter(get_config().models.role1, get_event_bus())


@lru_cache(maxsize=1)
def get_session_store() -> SessionStore:
    return SessionStore()


def get_trace_buffer_dep() -> DebugTraceBuffer:
    # Ensure config (and therefore the buffer) is initialized first.
    get_config()
    from shopping_agent.debug.trace import get_trace_buffer
    return get_trace_buffer()
