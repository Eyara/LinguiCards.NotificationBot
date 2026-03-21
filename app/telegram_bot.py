from __future__ import annotations

import logging
import re
from datetime import time as dtime
from zoneinfo import ZoneInfo, available_timezones

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from app.config import Settings
from app.daily_goal import DailyNotificationClient
from app.db.repository import Repository
from app.db.session import Database
from app.formatting import build_diff_message, format_current_status
from app.health import HealthClient, extract_status

logger = logging.getLogger(__name__)

_DAILY_REMINDER_JOB_PREFIX = "daily_goal_reminder:"


def _daily_reminder_job_name(chat_id: int) -> str:
    return f"{_DAILY_REMINDER_JOB_PREFIX}{chat_id}"


def _parse_hhmm(s: str) -> tuple[int, int] | None:
    s = s.strip()
    if not re.fullmatch(r"\d{1,2}:\d{2}", s):
        return None
    parts = s.split(":")
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h, m


def _reminder_clock_time(reminder_time: str, reminder_timezone: str) -> dtime:
    parsed = _parse_hhmm(reminder_time)
    if parsed is None:
        raise ValueError("invalid time")
    h, m = parsed
    tz = ZoneInfo(reminder_timezone)
    return dtime(hour=h, minute=m, tzinfo=tz)


class BotApp:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db = Database(settings.database_url)
        self._repo: Repository | None = None
        self._health = HealthClient(settings.api_base_url)
        self._daily = DailyNotificationClient(settings.api_base_url)

    @property
    def repo(self) -> Repository:
        if self._repo is None:
            raise RuntimeError("Repository not initialized yet")
        return self._repo

    async def init(self) -> None:
        await self._db.init()
        self._repo = Repository(self._db.sessionmaker)

    async def _post_init_application(self, application: Application) -> None:
        await self.init()
        await self._schedule_all_daily_reminders(application)

    async def _schedule_all_daily_reminders(self, application: Application) -> None:
        subscribers = await self.repo.list_subscribers_for_daily_reminders()
        logger.info("Scheduling %d daily goal reminder job(s)", len(subscribers))
        for sub in subscribers:
            await self._reschedule_daily_reminder_job(application, sub.chat_id)

    async def _reschedule_daily_reminder_job(self, application: Application, chat_id: int) -> None:
        name = _daily_reminder_job_name(chat_id)
        for job in application.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

        sub = await self.repo.get_subscriber(chat_id)
        if (
            sub is None
            or not sub.linguicards_username
            or not sub.reminder_time
            or not sub.reminder_timezone
        ):
            return

        try:
            t = _reminder_clock_time(sub.reminder_time, sub.reminder_timezone)
        except Exception as exc:
            logger.error("Invalid reminder schedule for chat_id=%s: %s", chat_id, exc)
            return

        application.job_queue.run_daily(
            self.daily_reminder_callback,
            time=t,
            days=(0, 1, 2, 3, 4, 5, 6),
            chat_id=chat_id,
            name=name,
        )

    async def daily_reminder_callback(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        job = context.job
        if job is None or job.chat_id is None:
            return
        chat_id = job.chat_id
        sub = await self.repo.get_subscriber(chat_id)
        if (
            sub is None
            or not sub.linguicards_username
            or not sub.reminder_time
            or not sub.reminder_timezone
        ):
            return

        try:
            status = await self._daily.fetch(sub.linguicards_username)
        except Exception as exc:
            logger.warning("Daily goal API failed for chat_id=%s: %s", chat_id, exc)
            return

        if status.is_goal_completed:
            return

        text = (
            "Напоминание о дневной цели: вы ещё не выполнили сегодняшнюю цель.\n"
            f"Прогресс: {status.gained_xp} / {status.target_xp} XP."
        )
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as exc:
            logger.error("Failed to send daily reminder to chat_id=%s: %s", chat_id, exc)

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
            text = "🚀 Бот запущен. Текущее состояние:\n\n" + format_current_status(current)
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
            "Вы подписаны на уведомления о состоянии LinguiCards.API.\n"
            "Мы сообщим, когда статус здоровья сервиса изменится.\n\n"
            "Команда /status — текущее состояние.\n\n"
            "Напоминания о дневной цели:\n"
            "/setusername — привязать имя пользователя LinguiCards\n"
            "/setdailyreminder ЧЧ:ММ Часовой_пояс — например: 21:00 Europe/Berlin\n"
            "/myreminder — показать настройки напоминаний\n"
            "/cleardailyreminder — отключить ежедневные напоминания"
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
                text = f"Код ответа HTTP {resp.status_code}\n\n{resp.text[:500]}"
        except Exception as exc:
            text = f"Не удалось обратиться к health: {exc}"
        await update.message.reply_text(text)

    async def setusername_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(
                "Использование: /setusername <имя_пользователя_linguicards>"
            )
            return
        username = context.args[0].strip()
        if not username:
            await update.message.reply_text("Имя пользователя не может быть пустым.")
            return
        chat_id = update.effective_chat.id
        await self.repo.set_linguicards_username(chat_id, username)
        await self._reschedule_daily_reminder_job(context.application, chat_id)
        await update.message.reply_text(f"Имя пользователя LinguiCards сохранено: {username}")

    async def setdailyreminder_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "Использование: /setdailyreminder ЧЧ:ММ IANA_часовой_пояс\n"
                "Пример: /setdailyreminder 21:00 Europe/Berlin"
            )
            return
        hhmm = context.args[0].strip()
        tz_name = context.args[1].strip()
        if _parse_hhmm(hhmm) is None:
            await update.message.reply_text("Неверное время. Укажите в формате ЧЧ:ММ (например 21:00).")
            return
        if tz_name not in available_timezones():
            await update.message.reply_text(
                "Неизвестный часовой пояс. Укажите имя по IANA, например Europe/Berlin или America/New_York."
            )
            return

        chat_id = update.effective_chat.id
        await self.repo.set_daily_reminder(chat_id, hhmm, tz_name)
        await self._reschedule_daily_reminder_job(context.application, chat_id)
        await update.message.reply_text(
            f"Ежедневное напоминание: {hhmm} ({tz_name}). "
            "Сработает, когда указано имя пользователя LinguiCards (/setusername)."
        )

    async def cleardailyreminder_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        await self.repo.clear_daily_reminder(chat_id)
        await self._reschedule_daily_reminder_job(context.application, chat_id)
        await update.message.reply_text("Расписание напоминаний о дневной цели сброшено.")

    async def myreminder_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        sub = await self.repo.get_subscriber(chat_id)
        if sub is None:
            await update.message.reply_text("Данных пока нет. Сначала выполните /start.")
            return
        lines = [
            f"Имя пользователя LinguiCards: {sub.linguicards_username or '(не задано)'}",
            f"Время напоминания: {sub.reminder_time or '(не задано)'}",
            f"Часовой пояс: {sub.reminder_timezone or '(не задано)'}",
        ]
        await update.message.reply_text("\n".join(lines))

    def build_application(self) -> Application:
        builder = (
            Application.builder()
            .token(self._settings.telegram_bot_token)
            .post_init(self._post_init_application)
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
        app.add_handler(CommandHandler("setusername", self.setusername_command))
        app.add_handler(CommandHandler("setdailyreminder", self.setdailyreminder_command))
        app.add_handler(CommandHandler("cleardailyreminder", self.cleardailyreminder_command))
        app.add_handler(CommandHandler("myreminder", self.myreminder_command))

        interval_seconds = self._settings.health_check_interval_minutes * 60
        app.job_queue.run_repeating(self.poll_health, interval=interval_seconds, first=10)

        return app
