import os

from dotenv import load_dotenv
from redis import Redis
from redis_entraid.cred_provider import (
    create_from_default_azure_credential,
)

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", "10000"))


def main():
    if not REDIS_HOST:
        raise ValueError("REDIS_HOST is missing")

    # Authenticate using your Azure CLI / Entra identity.
    credential_provider = create_from_default_azure_credential(
        ("https://redis.azure.com/.default",)
    )

    # Your Azure Managed Redis uses OSSCluster.
    client = Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        ssl=True,
        ssl_cert_reqs="required",
        credential_provider=credential_provider,
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=10,
    )

    try:
        # Test 1: Connection
        print("PING:", client.ping())

        # Test 2: Store temporary data
        client.set(
            "danube:connection:test",
            "Hello from Danube Chatbot",
            ex=60,
        )

        # Test 3: Retrieve data
        value = client.get("danube:connection:test")

        print("Stored value:", value)
        print("Redis connected successfully!")

    finally:
        client.close()


if __name__ == "__main__":
    main()