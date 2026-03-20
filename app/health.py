from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HealthClient:
    def __init__(self, api_base_url: str) -> None:
        self._base = api_base_url.rstrip("/")

    async def fetch(self) -> dict[str, Any]:
        headers = {"Accept": "application/json", "User-Agent": "LinguiCards-NotificationBot/1.0"}
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            resp = await client.get(f"{self._base}/health")
            logger.info("Health endpoint returned HTTP %d", resp.status_code)
            try:
                return resp.json()
            except Exception:
                logger.error("Non-JSON response body: %s", resp.text[:500])
                raise


def extract_status(health_data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"overall": health_data.get("status", "Unknown")}
    checks = health_data.get("checks", {})
    for name, info in checks.items():
        result[name] = {"status": info.get("status", "Unknown"), "error": info.get("error")}
    return result

