import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")
HEALTH_CHECK_INTERVAL_MINUTES = int(os.getenv("HEALTH_CHECK_INTERVAL_MINUTES", "5"))

SUBSCRIBERS_FILE = Path(__file__).parent / "subscribers.json"

previous_status: dict[str, Any] | None = None
subscribers: set[int] = set()


def _validate_config() -> None:
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not API_BASE_URL:
        missing.append("API_BASE_URL")
    if missing:
        sys.exit(f"Missing required environment variables: {', '.join(missing)}")


def load_subscribers() -> None:
    global subscribers
    if SUBSCRIBERS_FILE.exists():
        try:
            data = json.loads(SUBSCRIBERS_FILE.read_text(encoding="utf-8"))
            subscribers = set(data)
        except (json.JSONDecodeError, TypeError):
            subscribers = set()


def save_subscribers() -> None:
    SUBSCRIBERS_FILE.write_text(
        json.dumps(sorted(subscribers)), encoding="utf-8"
    )


def _extract_status(health_data: dict[str, Any]) -> dict[str, Any]:
    """Flatten health response into a comparable structure."""
    result: dict[str, Any] = {"overall": health_data.get("status", "Unknown")}
    checks = health_data.get("checks", {})
    for name, info in checks.items():
        result[name] = {
            "status": info.get("status", "Unknown"),
            "error": info.get("error"),
        }
    return result


def build_diff_message(
    old: dict[str, Any], new: dict[str, Any]
) -> str | None:
    """Return a human-readable message if status changed, or None."""
    if old == new:
        return None

    lines: list[str] = []
    new_overall = new.get("overall", "Unknown")
    old_overall = old.get("overall", "Unknown")

    if new_overall == "Healthy" and old_overall != "Healthy":
        lines.append("\u2705 LinguiCards.API is back to Healthy!")
    elif new_overall != old_overall:
        lines.append(
            "\u26a0\ufe0f LinguiCards.API health status changed!\n"
            f"Overall: {old_overall} \u2192 {new_overall}"
        )
    else:
        lines.append("\u26a0\ufe0f LinguiCards.API health check update:")

    check_names = sorted(set(list(old.keys()) + list(new.keys())) - {"overall"})
    if check_names:
        lines.append("\nChecks:")
    for name in check_names:
        old_check = old.get(name, {})
        new_check = new.get(name, {})
        old_s = old_check.get("status", "N/A") if isinstance(old_check, dict) else "N/A"
        new_s = new_check.get("status", "N/A") if isinstance(new_check, dict) else "N/A"
        new_err = new_check.get("error") if isinstance(new_check, dict) else None

        if old_s != new_s:
            lines.append(f"  \u2022 {name}: {old_s} \u2192 {new_s}")
        else:
            lines.append(f"  \u2022 {name}: {new_s}")

        if new_err:
            lines.append(f"    Error: {new_err}")

    return "\n".join(lines)


def format_current_status(status: dict[str, Any]) -> str:
    lines = [f"Overall: {status.get('overall', 'Unknown')}"]
    check_names = sorted(set(status.keys()) - {"overall"})
    if check_names:
        lines.append("\nChecks:")
    for name in check_names:
        info = status.get(name, {})
        if isinstance(info, dict):
            s = info.get("status", "Unknown")
            err = info.get("error")
            lines.append(f"  \u2022 {name}: {s}")
            if err:
                lines.append(f"    Error: {err}")
        else:
            lines.append(f"  \u2022 {name}: {info}")
    return "\n".join(lines)


async def fetch_health() -> dict[str, Any]:
    headers = {"Accept": "application/json", "User-Agent": "LinguiCards-NotificationBot/1.0"}
    async with httpx.AsyncClient(timeout=30, headers=headers) as client:
        resp = await client.get(f"{API_BASE_URL}/health")
        logger.info("Health endpoint returned HTTP %d", resp.status_code)
        try:
            return resp.json()
        except Exception:
            logger.error("Non-JSON response body: %s", resp.text[:500])
            raise


async def poll_health(context: ContextTypes.DEFAULT_TYPE) -> None:
    global previous_status

    try:
        health_data = await fetch_health()
        current = _extract_status(health_data)
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        current = {"overall": "Unreachable"}

    if previous_status is None:
        logger.info("Initial health status: %s", current.get("overall"))
        text = "\U0001f680 Bot started. Current health:\n\n" + format_current_status(current)
    else:
        diff = build_diff_message(previous_status, current)
        text = diff

    if text:
        logger.info("Notifying %d subscriber(s)", len(subscribers))
        for chat_id in list(subscribers):
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
            except Exception as exc:
                logger.error("Failed to notify %s: %s", chat_id, exc)

    previous_status = current


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    save_subscribers()
    await update.message.reply_text(
        "Subscribed to LinguiCards.API health notifications.\n"
        "You will be notified when the health status changes.\n\n"
        "Use /status to check current health."
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    headers = {"Accept": "application/json", "User-Agent": "LinguiCards-NotificationBot/1.0"}
    try:
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            resp = await client.get(f"{API_BASE_URL}/health")
        try:
            health_data = resp.json()
            current = _extract_status(health_data)
            text = format_current_status(current)
        except Exception:
            text = f"HTTP {resp.status_code}\n\n{resp.text[:500]}"
    except Exception as exc:
        text = f"Failed to reach health endpoint: {exc}"
    await update.message.reply_text(text)


def main() -> None:
    _validate_config()
    load_subscribers()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))

    interval_seconds = HEALTH_CHECK_INTERVAL_MINUTES * 60
    app.job_queue.run_repeating(
        poll_health, interval=interval_seconds, first=10
    )
    logger.info(
        "Bot started. Polling %s/health every %d minute(s).",
        API_BASE_URL,
        HEALTH_CHECK_INTERVAL_MINUTES,
    )

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
