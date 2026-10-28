import os
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from pathlib import Path
from dotenv import load_dotenv
from fastapi.exceptions import RequestValidationError

from app.core.clients import (
    create_service_clients,
    close_service_clients,
)
from app.core.startup_checks import run_startup_checks
from app.core.keyvault import load_application_secrets
from app.observability.app_insights import setup_application_insights

from app.api.v1.router import api_router
from app.middleware.correlation_id import correlation_id_middleware
from app.middleware.exception_handlers import register_exception_handlers
from app.scripts.cache_scheduler import create_cache_scheduler
from app.scripts.refresh_api_cache import (
    refresh_marketing_cache,
    refresh_currency_cache,
)
from app.persistence.redis_store import RedisCacheKeys
from app.templates.dev.chat_harness import router as dev_router

from app.middleware.exception_handlers import validation_exception_handler
from app.services.walkthrough_access_service import WalkthroughEngine
from app.observability.logger import setup_logging, audit_event


load_dotenv()
setup_logging()

logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting Danube Chatbot Backend")

    scheduler = None
    clients = None
    
    try:
        # Step 1: Load centralized application secrets
        secrets = await load_application_secrets()

        logger.info(
            "STARTUP_CHECK | service=keyvault | status=healthy"
        )

        # Step 2: Initialize Application Insights
        app_insights_initialized = setup_application_insights(
            connection_string=(
                secrets.applicationinsights_connection_string
                .get_secret_value()
            )
        )

        # Step 3: Create external service clients
        clients = await create_service_clients(secrets)

        app.state.clients = clients

        # Step 4: Run startup checks
        startup_status = await run_startup_checks(
            clients,
            application_insights_initialized=(
                app_insights_initialized
            ),
        )

        # Step 5: Log individual service statuses
        for service_name, status in startup_status.items():

            audit_event(
                "AZURE_SERVICE_HEALTH",
                service=service_name,
                status=status,
                healthy=(status == "healthy"),
            )

            log_method = (
                logger.info
                if status == "healthy"
                else logger.error
            )

            log_method(
                "STARTUP_CHECK | service=%s | status=%s",
                service_name,
                status,
            )

        # Step 6: Identify unhealthy services
        unhealthy_services = [
            service_name
            for service_name, status in startup_status.items()
            if status != "healthy"
        ]

        if unhealthy_services:
            logger.error(
                "STARTUP_CHECK_FAILED | unhealthy_services=%s",
                ",".join(unhealthy_services),
            )
        else:
            logger.info(
                "STARTUP_CHECK_SUCCESS | all services healthy"
            )

        # Step 7: Verify mandatory dependencies
        mandatory_services = (
            "postgres",
            "redis",
            "pinecone",
            "azure_openai",
        )

        failed_mandatory_services = [
            service
            for service in mandatory_services
            if startup_status.get(service) != "healthy"
        ]

        if failed_mandatory_services:
            raise RuntimeError(
                "Application startup failed. "
                "Unhealthy mandatory services: "
                + ", ".join(failed_mandatory_services)
            )

        # Application Insights is non-blocking
        if not app_insights_initialized:
            logger.warning(
                "Application Insights is unavailable. "
                "Backend will continue running."
            )

        logger.info("Application startup completed")

        # Initialize Marketing Catalog if Redis cache is empty.
        catalog_key = RedisCacheKeys.MARKETING_CATALOG
        catalog_exists = await clients.redis.exists(catalog_key)

        if not catalog_exists:
            logger.info(
                "MARKETING_CACHE_MISSING | Starting initial refresh"
            )

            refresh_success = await refresh_marketing_cache(
                clients=clients,
                secrets=secrets,
            )

            if refresh_success:
                logger.info(
                    "MARKETING_CACHE_INITIALIZED_SUCCESSFULLY"
                )
            else:
                logger.error(
                    "MARKETING_CACHE_INITIALIZATION_FAILED"
                )

        else:
            logger.info(
                "MARKETING_CACHE_ALREADY_AVAILABLE"
            )

        # Initialize Currency Rates if Redis cache is empty.
        currency_key = RedisCacheKeys.CURRENCY_RATES

        currency_exists = await clients.redis.exists(
            currency_key
        )

        if not currency_exists:
            logger.info(
                "CURRENCY_CACHE_MISSING | Starting initial refresh"
            )

            currency_success = await refresh_currency_cache(
                clients=clients,
                secrets=secrets,
            )

            if currency_success:
                logger.info(
                    "CURRENCY_CACHE_INITIALIZED_SUCCESSFULLY"
                )
            else:
                logger.error(
                    "CURRENCY_CACHE_INITIALIZATION_FAILED"
                )
        else:
            logger.info(
                "CURRENCY_CACHE_ALREADY_AVAILABLE"
            )

        scheduler = create_cache_scheduler(
            clients=clients,
            secrets=secrets,
        )

        scheduler.start()

        for job in scheduler.get_jobs():
            logger.info(
                "CACHE_SCHEDULER_STARTED | job=%s | next_run=%s",
                job.id,
                job.next_run_time,
            )

        logger.info(
            "CACHE_SCHEDULER_STARTED | next_run=%s",
            scheduler.get_job("marketing_cache_refresh").next_run_time,
        )


        walkthrough_path = (
            Path(__file__).resolve().parent
            / "app"
            / "data"
            / "walkthrough"
        )

        app.state.walkthrough_engine = WalkthroughEngine(
            directory=walkthrough_path
        )
        # Step 8: Application starts serving requests
        yield

    except Exception:
        logger.exception(
            "Danube Chatbot startup or application lifecycle failed"
        )
        raise

    finally:
        if scheduler is not None and scheduler.running:
            scheduler.shutdown(wait=False)

        # Step 9: Close connections
        if clients is not None:
            await close_service_clients(clients)

        logger.info("Application shutdown completed")


app = FastAPI(
    title="Danube Chatbot Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.middleware("http")(correlation_id_middleware)

register_exception_handlers(app)

app.include_router(
    api_router,
    prefix="/api/v1",
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)

# Development-only HTML test harness
if os.getenv("ENABLE_DEV_HARNESS", "false").lower() == "true":
    app.include_router(dev_router)
