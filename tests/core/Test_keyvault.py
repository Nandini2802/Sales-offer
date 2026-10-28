
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.core.exceptions import (
    HttpResponseError,
    ServiceRequestError,
    ServiceResponseError,
)

from app.core.keyvault import (
    AppSecrets,
    KeyVaultService,
    is_retryable_error,
    load_application_secrets,
)


# --------------------------------------------------
# Test fixtures
# --------------------------------------------------

@pytest.fixture
def mock_settings():
    return SimpleNamespace(
        environment="development",
        key_vault_url="https://test-vault.vault.azure.net/",
        retry_attempts=3,
        retry_min_wait_seconds=0,
        retry_max_wait_seconds=0,
    )


@pytest.fixture
def mock_azure_clients(mock_settings):
    """
    Replace Azure SDK clients with fake objects.
    No real Azure connection is made.
    """
    with (
        patch(
            "app.core.keyvault.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "app.core.keyvault.DefaultAzureCredential"
        ) as credential_class,
        patch(
            "app.core.keyvault.SecretClient"
        ) as client_class,
    ):
        credential = MagicMock()
        credential.close = AsyncMock()
        credential_class.return_value = credential

        client = MagicMock()
        client.get_secret = AsyncMock()
        client.close = AsyncMock()
        client_class.return_value = client

        yield mock_settings, credential, client


# --------------------------------------------------
# 1. Local environment
# --------------------------------------------------

@pytest.mark.asyncio
async def test_load_local_secrets():

    settings = SimpleNamespace(environment="local")

    local_secrets = SimpleNamespace(
        postgres_url="postgresql://localhost/test",
        redis_url="redis://localhost:6379",
        pinecone_api_key="fake-pinecone-key",
    )

    with (
        patch(
            "app.core.keyvault.get_settings",
            return_value=settings,
        ),
        patch(
            "app.core.keyvault.get_local_secrets",
            return_value=local_secrets,
        ),
        patch(
            "app.core.keyvault.KeyVaultService"
        ) as keyvault_class,
    ):
        result = await load_application_secrets()

    assert isinstance(result, AppSecrets)
    assert result.postgres_url.get_secret_value() == (
        "postgresql://localhost/test"
    )
    assert result.redis_url.get_secret_value() == (
        "redis://localhost:6379"
    )
    assert result.pinecone_api_key.get_secret_value() == (
        "fake-pinecone-key"
    )

    keyvault_class.assert_not_called()


# --------------------------------------------------
# 2. Azure environment
# --------------------------------------------------

@pytest.mark.asyncio
async def test_load_azure_secrets(mock_settings):

    mock_settings.environment = "production"

    mock_service = MagicMock()
    mock_service.get_secret = AsyncMock(
        side_effect=[
            "postgresql://azure/test",
            "redis://azure:6379",
            "azure-pinecone-key",
        ]
    )
    mock_service.close = AsyncMock()

    with (
        patch(
            "app.core.keyvault.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "app.core.keyvault.KeyVaultService",
            return_value=mock_service,
        ),
    ):
        result = await load_application_secrets()

    assert result.postgres_url.get_secret_value() == (
        "postgresql://azure/test"
    )
    assert result.redis_url.get_secret_value() == (
        "redis://azure:6379"
    )
    assert result.pinecone_api_key.get_secret_value() == (
        "azure-pinecone-key"
    )

    assert mock_service.get_secret.await_count == 3
    mock_service.get_secret.assert_any_await("postgres-url")
    mock_service.get_secret.assert_any_await("redis-url")
    mock_service.get_secret.assert_any_await("pinecone-api-key")
    mock_service.close.assert_awaited_once()


# --------------------------------------------------
# 3. Missing Key Vault URL
# --------------------------------------------------

def test_missing_keyvault_url(mock_settings):

    mock_settings.key_vault_url = None

    with patch(
        "app.core.keyvault.get_settings",
        return_value=mock_settings,
    ):
        with pytest.raises(
            ValueError,
            match="KEY_VAULT_URL is not configured",
        ):
            KeyVaultService()


# --------------------------------------------------
# 4. Successfully retrieve a secret
# --------------------------------------------------

@pytest.mark.asyncio
async def test_get_secret_success(mock_azure_clients):

    _, _, client = mock_azure_clients

    client.get_secret.return_value = SimpleNamespace(
        value="test-secret-value"
    )

    service = KeyVaultService()

    try:
        result = await service.get_secret("test-secret")
        assert result == "test-secret-value"
        client.get_secret.assert_awaited_once_with(
            "test-secret"
        )
    finally:
        await service.close()


# --------------------------------------------------
# 5. Secret has no value
# --------------------------------------------------

@pytest.mark.asyncio
async def test_get_secret_empty_value(mock_azure_clients):

    _, _, client = mock_azure_clients

    client.get_secret.return_value = SimpleNamespace(
        value=None
    )

    service = KeyVaultService()

    try:
        with pytest.raises(
            ValueError,
            match="has no value",
        ):
            await service.get_secret("empty-secret")
    finally:
        await service.close()


# --------------------------------------------------
# 6. Retryable and non-retryable errors
# --------------------------------------------------

def test_retryable_network_errors():

    assert is_retryable_error(
        ServiceRequestError("Connection failed")
    )

    assert is_retryable_error(
        ServiceResponseError("Connection interrupted")
    )


@pytest.mark.parametrize(
    "status_code, expected",
    [
        (408, True),
        (429, True),
        (500, True),
        (502, True),
        (503, True),
        (504, True),
        (400, False),
        (401, False),
        (403, False),
        (404, False),
    ],
)
def test_http_error_classification(status_code, expected):

    error = HttpResponseError(
        message="Simulated Azure HTTP error"
    )

    error.status_code = status_code

    assert is_retryable_error(error) is expected

# --------------------------------------------------
# 7. Retry after temporary failure
# --------------------------------------------------

@pytest.mark.asyncio
async def test_get_secret_retries(mock_azure_clients):

    _, _, client = mock_azure_clients

    client.get_secret.side_effect = [
        ServiceRequestError("Temporary network error"),
        SimpleNamespace(value="recovered-secret"),
    ]

    service = KeyVaultService()

    try:
        result = await service.get_secret("test-secret")

        assert result == "recovered-secret"
        assert client.get_secret.await_count == 2
    finally:
        await service.close()


# --------------------------------------------------
# 8. Do not retry permanent errors
# --------------------------------------------------

@pytest.mark.asyncio
async def test_get_secret_does_not_retry_403(
    mock_azure_clients,
):

    _, _, client = mock_azure_clients

    error = HttpResponseError(
        message="Forbidden"
    )
    error.status_code = 403

    client.get_secret.side_effect = error

    service = KeyVaultService()

    try:
        with pytest.raises(HttpResponseError):
            await service.get_secret("test-secret")

        assert client.get_secret.await_count == 1

    finally:
        await service.close()

# --------------------------------------------------
# 9. Cleanup on failure
# --------------------------------------------------

@pytest.mark.asyncio
async def test_cleanup_when_loading_fails(mock_settings):

    mock_service = MagicMock()
    mock_service.get_secret = AsyncMock(
        side_effect=RuntimeError("Key Vault unavailable")
    )
    mock_service.close = AsyncMock()

    with (
        patch(
            "app.core.keyvault.get_settings",
            return_value=mock_settings,
        ),
        patch(
            "app.core.keyvault.KeyVaultService",
            return_value=mock_service,
        ),
    ):
        with pytest.raises(RuntimeError):
            await load_application_secrets()

    mock_service.close.assert_awaited_once()


# --------------------------------------------------
# 10. Azure SDK resources closed
# --------------------------------------------------

@pytest.mark.asyncio
async def test_close_azure_clients(mock_azure_clients):

    _, credential, client = mock_azure_clients

    service = KeyVaultService()
    await service.close()

    client.close.assert_awaited_once()
    credential.close.assert_awaited_once()
