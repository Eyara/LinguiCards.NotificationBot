import os
import sys
from dataclasses import dataclass
from urllib.parse import quote

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    api_base_url: str
    api_key: str | None
    health_check_interval_minutes: int
    database_url: str
    telegram_proxy_url: str | None


def api_request_headers(api_key: str | None) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "LinguiCards-NotificationBot/1.0"}
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def load_settings() -> Settings:
    load_dotenv()

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    api_base_url = os.getenv("API_BASE_URL", "").rstrip("/")
    api_key = os.getenv("API_KEY", "").strip() or os.getenv("X_API_KEY", "").strip() or None
    health_check_interval_minutes = int(os.getenv("HEALTH_CHECK_INTERVAL_MINUTES", "5"))
    database_url = os.getenv("DATABASE_URL", "")

    telegram_proxy_host = os.getenv("TELEGRAM_PROXY_HOST", "").strip()
    telegram_proxy_port = os.getenv("TELEGRAM_PROXY_PORT", "").strip()
    telegram_proxy_username = os.getenv("TELEGRAM_PROXY_USERNAME", "").strip()
    telegram_proxy_password = os.getenv("TELEGRAM_PROXY_PASSWORD", "").strip()

    has_any_proxy = any(
        [
            telegram_proxy_host,
            telegram_proxy_port,
            telegram_proxy_username,
            telegram_proxy_password,
        ]
    )
    telegram_proxy_url: str | None = None
    if has_any_proxy:
        # If proxy is provided, require all fields.
        missing_proxy_fields = []
        if not telegram_proxy_host:
            missing_proxy_fields.append("TELEGRAM_PROXY_HOST")
        if not telegram_proxy_port:
            missing_proxy_fields.append("TELEGRAM_PROXY_PORT")
        if not telegram_proxy_username:
            missing_proxy_fields.append("TELEGRAM_PROXY_USERNAME")
        if not telegram_proxy_password:
            missing_proxy_fields.append("TELEGRAM_PROXY_PASSWORD")
        if missing_proxy_fields:
            sys.exit(
                "Missing required proxy environment variables: "
                + ", ".join(missing_proxy_fields)
            )

        try:
            int(telegram_proxy_port)
        except ValueError:
            sys.exit("TELEGRAM_PROXY_PORT must be an integer")

        # URL-encode user/pass; they may include special characters.
        user = quote(telegram_proxy_username, safe="")
        password = quote(telegram_proxy_password, safe="")
        telegram_proxy_url = (
            f"http://{user}:{password}@{telegram_proxy_host}:{telegram_proxy_port}"
        )

    missing: list[str] = []
    if not telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not api_base_url:
        missing.append("API_BASE_URL")
    if not database_url:
        missing.append("DATABASE_URL")
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")

    return Settings(
        telegram_bot_token=telegram_bot_token,
        api_base_url=api_base_url,
        api_key=api_key,
        health_check_interval_minutes=health_check_interval_minutes,
        database_url=database_url,
        telegram_proxy_url=telegram_proxy_url,
    )

