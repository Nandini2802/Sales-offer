from app.core.config import get_settings
from app.core.keyvault import AppSecrets
from app.services.inventory_token_service import InventoryTokenService


def get_inventory_token_service(
    secrets: AppSecrets,
) -> InventoryTokenService:

    settings = get_settings()

    # Test cookie is allowed only for local development.
    cookie = None

    if settings.environment == "local":
        cookie = (
            secrets.inventory_test_cookie.get_secret_value()
            or None
        )

    return InventoryTokenService(
        token_url=settings.inventory_auth_url,
        client_id=secrets.inventory_client_id.get_secret_value(),
        client_secret=secrets.inventory_client_secret.get_secret_value(),
        cookie=cookie,
    )