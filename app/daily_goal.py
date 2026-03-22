from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import api_request_headers

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyNotificationStatus:
    username: str
    is_goal_completed: bool
    gained_xp: int
    target_xp: int


class DailyNotificationClient:
    """GET /api/Notification/daily?username=..."""

    def __init__(self, api_base_url: str, api_key: str | None) -> None:
        self._base = api_base_url.rstrip("/")
        self._api_key = api_key

    async def fetch(self, username: str) -> DailyNotificationStatus:
        headers = api_request_headers(self._api_key)
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            resp = await client.get(
                f"{self._base}/api/Notification/daily",
                params={"username": username},
            )
            resp.raise_for_status()
            data = resp.json()
        return DailyNotificationStatus(
            username=str(data.get("username", username)),
            is_goal_completed=bool(data.get("isGoalCompleted", False)),
            gained_xp=int(data.get("gainedXp", 0)),
            target_xp=int(data.get("targetXp", 0)),
        )
