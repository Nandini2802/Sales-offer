import asyncio
import logging
import time
from typing import Any

from curl_cffi.requests import AsyncSession

logger = logging.getLogger(__name__)


class InventoryTokenService:
    def __init__(
        self,
        token_url: str,
        client_id: str,
        client_secret: str,
        cookie: str | None = None,
        refresh_margin_seconds: int = 120,
    ) -> None:
        if not token_url.startswith("https://"):
            raise ValueError("Inventory token URL must use HTTPS")
        if not client_id or not client_secret:
            raise ValueError("Inventory client credentials are missing")
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.cookie = cookie
        self.refresh_margin_seconds = refresh_margin_seconds
        self._token: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    async def get_token(self) -> str:
        if self._token and time.monotonic() < self._expires_at:
            return self._token

        async with self._lock:
            if self._token and time.monotonic() < self._expires_at:
                return self._token

            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if self.cookie:
                headers["Cookie"] = f"sess_map={self.cookie}"

            async with AsyncSession() as session:
                response = await session.post(
                    self.token_url,
                    headers=headers,
                    json={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    timeout=30,
                )

            if response.status_code != 200:
                logger.error("Inventory token request failed: HTTP %s", response.status_code)
                raise RuntimeError(f"Inventory token request failed: HTTP {response.status_code}")

            try:
                payload: Any = response.json()
            except ValueError as exc:
                raise RuntimeError("Inventory token API returned invalid JSON") from exc

            if not isinstance(payload, dict):
                raise RuntimeError("Inventory token API returned unexpected JSON")

            # Support common OAuth response, plus a nested data wrapper.
            # Confirm actual shape from a redacted response before deployment.
            source = payload.get("data", payload)
            if not isinstance(source, dict):
                raise RuntimeError("Inventory token API returned unexpected data")
            token = source.get("access_token") or source.get("accessToken")
            if not isinstance(token, str) or not token.strip():
                raise RuntimeError(
                    "No access_token in response. Check the redacted token API response structure."
                )
            expires_in = source.get("expires_in", source.get("expiresIn", 3600))
            try:
                lifetime = int(expires_in)
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Invalid token expiration returned by auth API") from exc
            if lifetime <= 0:
                raise RuntimeError("Token expiration must be positive")

            self._token = token.strip()
            self._expires_at = time.monotonic() + max(
                1, lifetime - min(self.refresh_margin_seconds, lifetime // 2)
            )
            logger.info("Inventory token obtained successfully; lifetime=%s seconds", lifetime)
            return self._token
