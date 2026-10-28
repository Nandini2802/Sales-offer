
"""
Standalone Application Insights integration test.

Tests:
1. Load connection string from existing configuration.
2. Initialize Azure Application Insights.
3. Send INFO, WARNING, and ERROR logs.
4. Send a test exception.
5. Send a custom OpenTelemetry trace.
6. Flush telemetry before exiting.

Run:
    python test_app_insights.py
"""

import asyncio
import pytest
import logging
import time
import uuid

from opentelemetry import trace
from opentelemetry.sdk.trace import (
    TracerProvider,
)

from app.core.keyvault import load_application_secrets
from app.observability.app_insights import (
    setup_application_insights,
)


logger = logging.getLogger("app.test_app_insights")


async def main():

    print("\n========== APPLICATION INSIGHTS TEST ==========\n")

    # Step 1: Load secrets through existing configuration
    print("[1] Loading application secrets...")

    try:
        secrets = await load_application_secrets()

        connection_string = (
            secrets.applicationinsights_connection_string
            .get_secret_value()
        )

        if not connection_string:
            raise ValueError(
                "Application Insights connection string is empty"
            )

        print("PASS: Connection string loaded successfully")

    except Exception as exc:
        pytest.fail(f"FAIL: Secret loading failed: {type(exc).__name__}: {exc}")
        

    # Step 2: Initialize Application Insights
    print("\n[2] Initializing Application Insights...")

    try:
        initialized = setup_application_insights(
            connection_string=connection_string
        )

        if not initialized:
            raise RuntimeError(
                "Application Insights initialization returned False"
            )

        print("PASS: Application Insights initialized")

    except Exception as exc:
        pytest.fail(f"FAIL: Initialization failed: {type(exc).__name__}: {exc}")

    # Unique ID to identify this test in Azure
    test_id = str(uuid.uuid4())

    print(f"\nTest ID: {test_id}")

    # Step 3: Send application logs
    print("\n[3] Sending test logs...")

    logger.info(
        "DANUBE_APPINSIGHTS_TEST INFO | test_id=%s",
        test_id,
    )

    logger.warning(
        "DANUBE_APPINSIGHTS_TEST WARNING | test_id=%s",
        test_id,
    )

    logger.error(
        "DANUBE_APPINSIGHTS_TEST ERROR | test_id=%s",
        test_id,
    )

    print("PASS: Test log calls executed")

    # Step 4: Test exception logging
    print("\n[4] Sending test exception...")

    try:
        raise ValueError(
            "DANUBE_APPINSIGHTS_TEST sample exception"
        )

    except ValueError:
        logger.exception(
            "DANUBE_APPINSIGHTS_TEST EXCEPTION | test_id=%s",
            test_id,
        )

    print("PASS: Test exception logged")

    # Step 5: Test distributed tracing
    print("\n[5] Creating OpenTelemetry trace...")

    tracer = trace.get_tracer("app.test_app_insights")

    with tracer.start_as_current_span(
        "danube.application_insights.test"
    ) as span:

        span.set_attribute(
            "test.id",
            test_id,
        )

        span.set_attribute(
            "service.component",
            "application_insights",
        )

        span.add_event(
            "Application Insights test trace created"
        )

        logger.info(
            "DANUBE_APPINSIGHTS_TEST TRACE | test_id=%s",
            test_id,
        )

    print("PASS: Trace created")

    # Step 6: Flush trace telemetry
    print("\n[6] Flushing telemetry...")

    provider = trace.get_tracer_provider()

    if isinstance(provider, TracerProvider):
        flushed = provider.force_flush(timeout_millis=15000)
        print(f"Trace flush result: {flushed}")

    # Allow batched log export to complete.
    await asyncio.sleep(20)

    print("\n========== TEST FINISHED ==========")
    print(f"Search Azure logs using test ID: {test_id}")
    print("Check Application Insights -> Logs")
    print(
        "\nNote: Successful execution does not guarantee "
        "Azure has ingested the telemetry."
    )


@pytest.mark.asyncio
async def test_application_insights_integration():
    await main()
