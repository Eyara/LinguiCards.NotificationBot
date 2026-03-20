from __future__ import annotations

import logging
from typing import Any

import httpx
from telegram import Update
from telegram.request import HTTPXRequest
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import Settings
from app.db.repository import Repository
from app.db.session import Database
from app.formatting import build_diff_message, format_current_status
from app.health import HealthClient, extract_status

logger = logging.getLogger(__name__)


class BotApp:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db = Database(settings.database_url)
        self._repo: Repository | None = None
        self._health = HealthClient(settings.api_base_url)

    @property
    def repo(self) -> Repository:
        if self._repo is None:
            raise RuntimeError("Repository not initialized yet")
        return self._repo

    async def init(self) -> None:
        await self._db.init()
        self._repo = Repository(self._db.sessionmaker)

    async def poll_health(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            health_data = await self._health.fetch()
            current = extract_status(health_data)
        except Exception as exc1:
           logger.error("Health check failed (attempt 1): %s", exc1)
            try:
                health_data = await self._health.fetch()
                current = extract_status(health_data)
            except Exception as exc2:
                logger.error("Health check failed (attempt 2): %s", exc2)
                current = {"overall": "Unhealthy"}

        previous = await self.repo.get_health_state()
        if previous is None:
            text = "🚀 Bot started. Current health:\n\n" + format_current_status(current)
        else:
            text = build_diff_message(previous, current)

        await self.repo.set_health_state(current)

        if text:
            chat_ids = await self.repo.list_subscribers()
            logger.info("Notifying %d subscriber(s)", len(chat_ids))
            for chat_id in chat_ids:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=text)
                except Exception as exc:
                    logger.error("Failed to notify %s: %s", chat_id, exc)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        await self.repo.add_subscriber(chat_id)
        await update.message.reply_text(
            "Subscribed to LinguiCards.API health notifications.\n"
            "You will be notified when the health status changes.\n\n"
            "Use /status to check current health."
        )

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        headers = {"Accept": "application/json", "User-Agent": "LinguiCards-NotificationBot/1.0"}
        try:
            async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                resp = await client.get(f"{self._settings.api_base_url.rstrip('/')}/health")
            try:
                health_data = resp.json()
                current = extract_status(health_data)
                text = format_current_status(current)
            except Exception:
                text = f"HTTP {resp.status_code}\n\n{resp.text[:500]}"
        except Exception as exc:
            text = f"Failed to reach health endpoint: {exc}"
        await update.message.reply_text(text)

    def build_application(self) -> Application:
        builder = (
            Application.builder()
            .token(self._settings.telegram_bot_token)
            .post_init(lambda _: self.init())
        )
        
        if self._settings.telegram_proxy_url:
            request = HTTPXRequest(
                proxy=self._settings.telegram_proxy_url,
                connect_timeout=30,
                read_timeout=30,
                write_timeout=30,
            )
            builder = builder.request(request).get_updates_request(request)

        app = builder.build()

        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("status", self.status_command))

        interval_seconds = self._settings.health_check_interval_minutes * 60
        app.job_queue.run_repeating(self.poll_health, interval=interval_seconds, first=10)

        return app

