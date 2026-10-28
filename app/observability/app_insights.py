import logging

from azure.monitor.opentelemetry import configure_azure_monitor

logger = logging.getLogger(__name__)

_application_insights_initialized = False


def setup_application_insights(
    connection_string: str,
) -> bool:

    global _application_insights_initialized

    if _application_insights_initialized:
        return True

    if not connection_string:
        logger.error(
            "Application Insights connection string is missing"
        )
        return False

    configure_azure_monitor(
        connection_string=connection_string,
        logger_name="app",
        enable_live_metrics=True,
        instrumentation_options={
            "azure_sdk": {"enabled": True},
            "django": {"enabled": False},
            "flask": {"enabled": False},
            "fastapi": {"enabled": True},
            "psycopg2": {"enabled": False},
            "requests": {"enabled": True},
            "urllib": {"enabled": True},
            "urllib3": {"enabled": True},
        },
    )

    _application_insights_initialized = True

    logger.info(
        "Application Insights initialized successfully"
    )

    return True
