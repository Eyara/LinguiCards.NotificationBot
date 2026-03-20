import logging

from telegram import Update

from app.config import load_settings
from app.telegram_bot import BotApp

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    bot_app = BotApp(settings)
    app = bot_app.build_application()

    logger.info(
        "Bot started. Polling %s/health every %d minute(s).",
        settings.api_base_url,
        settings.health_check_interval_minutes,
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
