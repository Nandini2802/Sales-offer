"""        
    Application configuration for the Danube Chatbot Backend.

    This module contains non-secret application configuration required for all environments.
    
    For local development, sensitive values are loaded separately from the .env file using LocalSecrets.

    For deployed environments such as development, UAT, and production,
    sensitive values are retrieved from Azure Key Vault.

"""


from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    """
        Define and validate non-secret application configuration.

        These settings are available across all environments and control
        application behaviour without containing sensitive credentials.

        REQUIRED = postgres_url: str
        OPTIONAL = key_vault_url: str | None = None
        HAS DEFAULT = request_timeout_seconds: int = 10
    """

    app_name: str = "Danube Chatbot Backend"
    environment: Literal["local", "development", "uat", "production"]
    debug: bool = False

    # Microsoft Foundry
    foundry_openai_base_url: str = ""
    foundry_openai_model: str = "gpt-5.4"
    foundry_openai_timeout_seconds: float = 30.0
    generation_openai_model: str = ""

    # Azure Key Vault
    key_vault_url: str | None = None

    # Bank Detail
    bank_details_api_url: str = ""
    bank_details_timeout_seconds: int = 45

    # Currency API
    currency_api_url: str = ""
    currency_cache_refresh_hours: int = 24
    currency_cache_ttl_seconds: int = 259200

    # Correlation ID Header
    correlation_id_header: str = "X-Correlation-ID"

    # Download Availability
    availability_api_url: str = ""
    availability_timeout_seconds: float = 60.0
    availability_app_version: str = "2.0.8"
    download_availability_rbac_enabled: bool = True

    # External APIs
    request_timeout_seconds: int = 10

    # History
    session_inactivity_minutes: int = 5

    # Inventory API
    inventory_project_api_url: str = ""
    inventory_units_api_url: str = ""
    inventory_timeout_seconds: float = 30.0
    inventory_max_retries: int = 3
    inventory_test_user_id: str | None = None
    inventory_auth_url: str = ""

    # Marketing API
    marketing_api_url: str = ""
    marketing_cache_ttl_seconds: int = 172800
    api_cache_refresh_hours: int = 12
    marketing_product_name: str = "Vendor"
    marketing_product_feature_name: str = "AMIRA"

    # MAP Link
    project_coordinates_api_url: str = ""

    # Portfolio API
    osf_portfolio_api_url: str = ""
    osf_portfolio_timeout_seconds: float = 30.0

    # Payment Plan
    payment_plan_api_url: str = ""
    payment_plan_timeout_seconds: float = 30.0

    # Pinecone
    pinecone_index_name: str | None = None

    # Project Discovery
    project_information_api_url: str = ""
    project_information_timeout_seconds: float = 45.0

    # Retry
    retry_attempts: int = 3
    retry_min_wait_seconds: float = 1
    retry_max_wait_seconds: float = 8

    # Sales Offer
    sales_offer_unit_details_url: str = ""
    sales_offer_generate_url: str = ""
    sales_offer_timeout_seconds: int = 45
    sales_offer_selection_ttl_seconds: int = 1800

    # Unit Comparison
    unit_comparison_api_url: str = ""
    unit_comparison_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

class LocalSecrets(BaseSettings):
    """
        Define sensitive values used only during local development.

        These values are loaded from the local .env file when the application
        is running with ENVIRONMENT=local.

        Deployed environments must retrieve the corresponding secrets from
        Azure Key Vault instead.
    """

    postgres_url: str
    redis_host: str
    redis_port: int
    pinecone_api_key: str
    applicationinsights_connection_string: str
    marketing_api_key: str
    foundry_openai_api_key: str
    currency_api_cookie: str = ""
    inventory_client_id: str = ""
    inventory_client_secret: str = ""
    inventory_test_cookie: str = ""
    osf_portfolio_api_key: str = ""
    google_maps_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )




@lru_cache
def get_settings() -> Settings:
    """
        Load and cache the application settings.

        The settings object is created once and reused throughout the application. 

        Returns:
            Settings: Validated and cached non-secret application configuration..
    """

    return Settings()

@lru_cache
def get_local_secrets() -> LocalSecrets:
    """
        Load, validate, and cache secrets for local development.

        This function should only be called when the application is running
        with ENVIRONMENT=local.

        Returns:
            LocalSecrets: Validated and cached local development secrets.
    """
    return LocalSecrets()


settings = get_settings()