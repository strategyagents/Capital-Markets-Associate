"""Telemetry helpers for emitting structured events to Graylog via OTLP gRPC."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggingHandler, LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from .config import get_settings

_TELEMETRY_INITIALIZED = False
_LOGGER = logging.getLogger("agent_codex")


def setup_telemetry(service_name: str) -> None:
    global _TELEMETRY_INITIALIZED
    if _TELEMETRY_INITIALIZED:
        return

    settings = get_settings()
    
    # Normalize endpoint format - ensure it's just host:port for gRPC
    endpoint = settings.graylog_endpoint
    if endpoint.startswith("http://"):
        endpoint = endpoint.replace("http://", "")
    elif endpoint.startswith("https://"):
        endpoint = endpoint.replace("https://", "")
    
    # Log telemetry setup for debugging
    print(f"[Telemetry] Initializing for service: {service_name}, endpoint: {endpoint}, namespace: {settings.graylog_namespace}")
    
    try:
        resource = Resource(
            attributes={
                "service.name": service_name,
                "service.namespace": settings.graylog_namespace,
            }
        )

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=endpoint,
                    insecure=settings.graylog_insecure,
                )
            )
        )
        trace.set_tracer_provider(tracer_provider)

        logger_provider = LoggerProvider(resource=resource)
        log_exporter = OTLPLogExporter(
            endpoint=endpoint,
            insecure=settings.graylog_insecure,
        )
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(log_exporter)
        )
        
        # Create handler and attach to root logger
        # The LoggingHandler will use the logger_provider passed to it
        handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Remove any existing handlers to avoid duplicates
        root_logger.handlers.clear()
        root_logger.addHandler(handler)
        
        # Ensure the agent_codex logger also inherits and propagates
        _LOGGER.setLevel(logging.INFO)
        _LOGGER.propagate = True

        _TELEMETRY_INITIALIZED = True
        print(f"[Telemetry] Successfully initialized telemetry for {service_name}")
        
        # Send a test log to verify connection
        _LOGGER.info("telemetry.initialized", extra={
            "service": service_name,
            "endpoint": endpoint,
            "namespace": settings.graylog_namespace
        })
    except Exception as e:
        print(f"[Telemetry] ERROR: Failed to initialize telemetry: {e}")
        # Don't fail the application if telemetry setup fails
        import traceback
        traceback.print_exc()


def log_agent_event(event: str, **details: Any) -> None:
    payload = {"event": event, **details}
    _LOGGER.info(event, extra={"event": event, "payload": payload})


def record_model_payload(agent_name: str, stage: str, payload: Dict[str, Any]) -> None:
    try:
        serialized = json.dumps(payload)
    except TypeError:
        serialized = str(payload)
    log_agent_event(
        "model.io",
        agent=agent_name,
        stage=stage,
        payload=serialized,
    )


def record_tool_invocation(agent_name: str, tool_name: str, status: str, **metadata: Any) -> None:
    log_agent_event(
        "tool.invocation",
        agent=agent_name,
        tool=tool_name,
        status=status,
        metadata=metadata,
    )
