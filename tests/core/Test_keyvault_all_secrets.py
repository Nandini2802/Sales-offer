
import pytest

from app.core.config import get_settings
from app.core.keyvault import load_application_secrets


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_secrets_from_keyvault():

    settings = get_settings()

    # Ensure test does not silently use local .env secrets
    assert settings.environment == "development", (
        "Set ENVIRONMENT=development before running this test"
    )

    assert settings.key_vault_url, (
        "KEY_VAULT_URL is missing"
    )

    # This calls the actual Key Vault loading function
    secrets = await load_application_secrets()

    # Validate all seven returned values
    assert secrets.postgres_url.get_secret_value()
    print("PASS: PostgreSQL URL retrieved")

    assert secrets.redis_host
    print("PASS: Redis host retrieved")

    assert 1 <= secrets.redis_port <= 65535
    print("PASS: Redis port retrieved")

    assert secrets.pinecone_api_key.get_secret_value()
    print("PASS: Pinecone API key retrieved")

    assert secrets.applicationinsights_connection_string.get_secret_value()
    print("PASS: Application Insights connection string retrieved")

    assert secrets.marketing_api_key.get_secret_value()
    print("PASS: Marketing API key retrieved")

    assert secrets.foundry_openai_api_key.get_secret_value()
    print("PASS: Foundry OpenAI API key retrieved")

    print("\nSUCCESS: All 7 secrets loaded from Azure Key Vault")
