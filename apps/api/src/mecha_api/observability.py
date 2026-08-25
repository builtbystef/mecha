"""OpenTelemetry tracing for requests, agent runs, tool calls, and logs.

Logfire is the OTel SDK: `logfire.configure()` installs the global tracer
provider that pydantic-ai's own instrumentation writes into. Spans reach
Logfire when `LOGFIRE_TOKEN` is set and any OTLP collector when
`OTEL_EXPORTER_OTLP_ENDPOINT` is set. With neither, nothing is exported and
the app behaves exactly as it did before — unconfigured is a supported state.
"""

import logging

import httpx
import logfire
from fastapi import FastAPI
from logfire.integrations.logging import LogfireLoggingHandler

from mecha_api.config import ObservabilitySettings


def configure(app: FastAPI) -> None:
    """Set up exporting, logging, and tracing. Call once, at import.

    Not in the lifespan: Starlette freezes the middleware stack before the
    lifespan runs, so `instrument_fastapi` would be too late to add its own.
    """
    settings = ObservabilitySettings()

    logfire.configure(
        service_name=settings.service_name,
        environment=settings.environment,
        send_to_logfire="if-token-present",
        # Off by default: span-per-line output is unreadable next to the dev
        # server's own logs. `None` means logfire's default (on).
        console=None if settings.trace_console else False,
    )

    # Keep stderr logs and add a second sink that turns records into span
    # events, so a `logger.exception` lands on the trace that failed.
    logging.basicConfig(level=settings.log_level)
    logging.getLogger().addHandler(LogfireLoggingHandler())

    # Agent runs, model requests, and tool calls. Prompts and replies ride
    # along as span attributes unless `trace_content` is off.
    logfire.instrument_pydantic_ai(include_content=settings.trace_content)

    # Health is polled by load balancers; tracing it is pure noise.
    logfire.instrument_fastapi(app, excluded_urls="/api/health")


def instrument_http_client(client: httpx.AsyncClient) -> None:
    """Trace the tools' outbound calls.

    Scoped to this client so provider traffic stays with the model spans
    pydantic-ai already emits, rather than being traced twice.
    """
    logfire.instrument_httpx(client)
