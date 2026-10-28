
import json
from unittest.mock import AsyncMock

import pytest

from app.services.api_cache_service import APICacheService


@pytest.mark.asyncio
async def test_cache_set():

    redis_client = AsyncMock()
    cache = APICacheService(redis_client)

    data = {
        "project": "Greenz",
        "material": "brochure",
    }

    await cache.set(
        key="test:marketing",
        data=data,
        ttl_seconds=3600,
    )

    redis_client.set.assert_awaited_once_with(
        "test:marketing",
        json.dumps(data, ensure_ascii=False),
        ex=3600,
    )


@pytest.mark.asyncio
async def test_cache_get_hit():

    redis_client = AsyncMock()

    redis_client.get.return_value = json.dumps({
        "project": "Greenz"
    })

    cache = APICacheService(redis_client)

    result = await cache.get("test:marketing")

    assert result == {
        "project": "Greenz"
    }


@pytest.mark.asyncio
async def test_cache_get_miss():

    redis_client = AsyncMock()
    redis_client.get.return_value = None

    cache = APICacheService(redis_client)

    result = await cache.get("missing:key")

    assert result is None


@pytest.mark.asyncio
async def test_cache_delete():

    redis_client = AsyncMock()
    redis_client.delete.return_value = 1

    cache = APICacheService(redis_client)

    result = await cache.delete("test:marketing")

    assert result is True
