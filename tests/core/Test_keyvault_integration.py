
"""
Integration test for Azure Key Vault.

This test connects to the real Azure Key Vault.
No mocking is used.
"""

import pytest

from app.core.keyvault import KeyVaultService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_keyvault_connection():

    service = KeyVaultService()

    try:
        secret_value = await service.get_secret(
            "danube-test-secret"
        )

        assert secret_value is not None

        assert secret_value == (
            "keyvault-connection-successful"
        )

        print(
            "\nSUCCESS: Connected to Azure Key Vault"
        )

        print(
            "SUCCESS: Retrieved and verified test secret"
        )

    finally:
        await service.close()
