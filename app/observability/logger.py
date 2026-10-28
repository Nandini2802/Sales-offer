import json
import logging
import os
import re
import sys
import hashlib
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from opentelemetry import trace


log_context = ContextVar("danube_log_context", default={})

SENSITIVE_KEYS = {
    "authorization",
    "access_token",
    "refresh_token",
    "api_key",
    "x_api_key",
    "password",
    "secret",
    "cookie",
    "encrypteddata",
    "bank_account",
    "account_number",
    "iban",
    "email",
    "phone",
}

SENSITIVE_CONTENT_KEYS = {
    "message",
    "user_message",
    "assistant_message",
    "response",
    "input",
    "output",
    "prompt",
    "history",
    "recent_conversation",
    "verified_service_results",
    "html",
    "files",
    "url",
    "download_url",
}

MESSAGE_LOGGING_EVENTS = {
    "CHAT_REQUEST_RECEIVED",
    "LLM1_COMPLETED",
    "LLM2_OUTPUT",
}


def prepare_audit_details(event_name, details):
    """
    Prepare event details for Application Insights.

    Only the three selected events may include message content.
    Other events continue using the existing masking rules.
    """

    if event_name not in MESSAGE_LOGGING_EVENTS:
        return safe_value(details)

    # This is a deliberately restricted allowlist.
    allowed_fields = {
        "correlation_id",
        "session_id",
        "user_id",
        "role",
        "source",
        "status",
        "latency_ms",
    }

    result = {
        key: safe_value(value, key)
        for key, value in details.items()
        if key in allowed_fields
    }

    for field in ("user_message", "llm1_response", "llm2_response"):
        if field in details:
            value = details[field]
            result[field] = str(value)[:10000]

    return result

def safe_value(value, key="", depth=0):
    """Prevent sensitive payloads from entering logs."""

    name = key.lower()

    if name in SENSITIVE_KEYS:
        return "[REDACTED]"

    if name in SENSITIVE_CONTENT_KEYS:
        return "[CONTENT_OMITTED]"

    if depth > 5:
        return "[MAX_DEPTH]"

    if isinstance(value, dict):
        return {
            str(k): safe_value(v, str(k), depth + 1)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            safe_value(item, depth=depth + 1)
            for item in value[:20]
        ]

    if isinstance(value, str):
        # Remove common credentials from arbitrary strings.
        value = re.sub(
            r"Bearer\s+\S+",
            "Bearer [REDACTED]",
            value,
            flags=re.IGNORECASE,
        )
        value = re.sub(
            r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
            "[EMAIL]",
            value,
        )
        return value[:500]

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    return str(type(value).__name__)


class JSONFormatter(logging.Formatter):

    def format(self, record):
        context = log_context.get()

        span = trace.get_current_span()
        span_context = span.get_span_context()

        payload = {
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(
                record,
                "event_name",
                "APPLICATION_LOG",
            ),
            "message": safe_value(
                record.getMessage()
            ),
            "correlation_id": context.get(
                "correlation_id"
            ),
            "session_id": context.get("session_id"),
            "trace_id": (
                format(span_context.trace_id, "032x")
                if span_context.is_valid
                else None
            ),
            "details": safe_value(
                getattr(record, "details", {})
            ),
        }

        if record.exc_info:
            exception_type, exception_value, exception_tb = record.exc_info

            payload["exception_type"] = exception_type.__name__

            payload["exception_message"] = safe_value(
                str(exception_value)
            )

            # Keep detailed tracebacks local during debugging.
            if os.getenv("LOG_FULL_TRACEBACK", "false").lower() == "true":
                payload["exception_traceback"] = self.formatException(
                    record.exc_info
                )

        payload["exception_message"] = safe_value(
            str(record.exc_info[1]) if record.exc_info else None
        )

        if record.exc_info and record.exc_info[2] is not None:
            payload["exception_traceback"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        )


def setup_logging():
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)

    # Avoid installing duplicate handlers.
    if getattr(app_logger, "_danube_configured", False):
        return app_logger

    formatter = JSONFormatter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    app_logger.addHandler(console_handler)

    # Optional local-development file.
    if os.getenv("ENABLE_FILE_LOGGING", "false").lower() == "true":
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        file_handler = RotatingFileHandler(
            log_dir / "danube_chatbot.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        app_logger.addHandler(file_handler)

    app_logger._danube_configured = True

    return app_logger


def audit_event(
    event_name,
    *,
    level="INFO",
    **details,
):
    logger = logging.getLogger("app.audit")

    prepared_details = prepare_audit_details(
        event_name,
        details
    )

    logger.log(
        getattr(logging, level.upper(), logging.INFO),
        event_name,
        extra={
            "event_name": event_name,
            "details": json.dumps(
                prepared_details,
                ensure_ascii=False,
                default=str,
            ),
        },
    )