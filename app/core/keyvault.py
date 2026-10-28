
"""
Azure Key Vault and application secret management.

Local environment:
    Load credentials from .env using get_local_secrets().

Deployed environments:
    Retrieve credentials from Azure Key Vault.

Responsibilities:
    - Authenticate with Azure Key Vault
    - Retrieve secrets with retry/backoff
    - Load environment-specific application secrets
    - Close Azure clients after use
"""

import logging
from pydantic import BaseModel, SecretStr

from azure.identity.aio import DefaultAzureCredential
from azure.keyvault.secrets.aio import SecretClient

from azure.core.exceptions import (
    ServiceRequestError,
    ServiceResponseError,
    HttpResponseError,
)

from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings, get_local_secrets


logger = logging.getLogger(__name__)

class AppSecrets(BaseModel):
    """
    Common secret structure for all environments.
    """

    postgres_url: SecretStr
    redis_host: str
    redis_port: int
    pinecone_api_key: SecretStr
    applicationinsights_connection_string: SecretStr
    marketing_api_key: SecretStr
    foundry_openai_api_key: SecretStr
    inventory_client_id: SecretStr
    inventory_client_secret: SecretStr
    inventory_test_cookie: SecretStr
    currency_api_cookie: SecretStr
    osf_portfolio_api_key: SecretStr
    google_maps_api_key: SecretStr


def is_retryable_error(exc: BaseException) -> bool:
    """
    Retry temporary network and Azure service failures.
    """

    if isinstance(
        exc,
        (ServiceRequestError, ServiceResponseError),
    ):
        return True

    if isinstance(exc, HttpResponseError):
        return exc.status_code in (
            408, 429, 500, 502, 503, 504
        )

    return False

class KeyVaultService:
    """
    Handles authentication and secret retrieval
    from Azure Key Vault.
    """

    def __init__(self):

        settings = get_settings()

        if not settings.key_vault_url:
            raise ValueError(
                "KEY_VAULT_URL is not configured"
            )

        self.settings = settings

        self.credential = DefaultAzureCredential()

        self.client = SecretClient(
            vault_url=settings.key_vault_url,
            credential=self.credential,
            retry_total=0,
        )

    async def get_secret(self, secret_name: str) -> str:
        """
        Retrieve a secret with retry and exponential backoff.
        """

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(
                    self.settings.retry_attempts
                ),
                wait=wait_exponential(
                    multiplier=1,
                    min=self.settings.retry_min_wait_seconds,
                    max=self.settings.retry_max_wait_seconds,
                ),
                retry=retry_if_exception(
                    is_retryable_error
                ),
                reraise=True,
            ):
                with attempt:

                    secret = await self.client.get_secret(
                        secret_name
                    )

                    if secret.value is None:
                        raise ValueError(
                            f"Secret '{secret_name}' has no value"
                        )

                    return secret.value

        except Exception:
            logger.exception(
                "Failed to retrieve Key Vault secret '%s'",
                secret_name,
            )
            raise

    async def close(self):
        """
        Close Azure SDK resources.
        """

        await self.client.close()
        await self.credential.close()


async def load_application_secrets() -> AppSecrets:
    """
    Load required application secrets.

    LOCAL:
        Read from .env using LocalSecrets.

    DEVELOPMENT / UAT / PRODUCTION:
        Read from Azure Key Vault.

    Returns:
        AppSecrets: Validated application credentials.
    """

    settings = get_settings()

    # Local development
    if settings.environment == "local":

        logger.info(
            "Loading application secrets from local environment"
        )

        local = get_local_secrets()

        return AppSecrets(
            postgres_url=local.postgres_url,
            redis_host=local.redis_host,
            redis_port=local.redis_port,
            pinecone_api_key=local.pinecone_api_key,
            applicationinsights_connection_string=local.applicationinsights_connection_string,
            marketing_api_key=local.marketing_api_key,
            foundry_openai_api_key=local.foundry_openai_api_key,
            inventory_client_id=local.inventory_client_id,
            inventory_client_secret=local.inventory_client_secret,
            inventory_test_cookie=local.inventory_test_cookie,
            currency_api_cookie=local.currency_api_cookie,
            osf_portfolio_api_key=local.osf_portfolio_api_key,
            google_maps_api_key=local.google_maps_api_key,
        )
    
    # Deployed environments
    logger.info(
        "Loading application secrets from Azure Key Vault"
    )

    keyvault = KeyVaultService()

    try:
        return AppSecrets(
            postgres_url=await keyvault.get_secret(
                "postgres-url"
            ),
            redis_host=await keyvault.get_secret(
                "redis-host"
            ),
            redis_port=int(
                await keyvault.get_secret("redis-port")
            ),
            pinecone_api_key=await keyvault.get_secret(
                "pinecone-api-key"
            ),
            applicationinsights_connection_string=(
                await keyvault.get_secret(
                    "applicationinsights-connection-string"
                )
            ),
            marketing_api_key=SecretStr(
                await keyvault.get_secret("marketing-api-key")
            ),
            foundry_openai_api_key=SecretStr(
                await keyvault.get_secret("foundry-openai-api-key")
            ),
            inventory_client_id=await keyvault.get_secret(
                "inventory-client-id"
            ),

            inventory_client_secret=await keyvault.get_secret(
                "inventory-client-secret"
            ),

            inventory_test_cookie=await keyvault.get_secret(
                "inventory-test-cookie"
            ),

            currency_api_cookie=await keyvault.get_secret(
                "currency-api-cookie"
            ),
            osf_portfolio_api_key=SecretStr(
                await keyvault.get_secret("osf-portfolio-api-key")
            ),
            google_maps_api_key=SecretStr(
                await keyvault.get_secret("google-maps-api-key")
            ),
        )
    
    finally:
        await keyvault.close()
