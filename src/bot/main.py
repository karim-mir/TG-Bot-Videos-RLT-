import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from src.bot import handlers
from src.config import TELEGRAM_BOT_TOKEN
from src.core.database import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class VideoStatsBot:
    """Класс для управления Telegram-ботом."""

    def __init__(self):
        """Инициализация бота."""
        self.bot = Bot(
            token=TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML")
        )
        self.dp = Dispatcher(storage=MemoryStorage())
        self._register_handlers()

    def _register_handlers(self):
        """Регистрация всех обработчиков."""
        self.dp.include_router(handlers.router)

    async def set_commands(self):
        """Установка меню команд бота."""

        commands = [
            BotCommand(command="/start", description="Запустить бота"),
            BotCommand(command="/stats", description="Общая статистика"),
            BotCommand(command="/top_videos", description="Топ видео"),
            BotCommand(command="/top_creators", description="Топ креаторов"),
            BotCommand(command="/video_info", description="Инфо о видео по ID"),
            BotCommand(command="/daily_growth", description="Рост за день"),
            BotCommand(command="/help", description="Помощь"),
        ]
        await self.bot.set_my_commands(commands)

    async def start(self):
        """Запуск бота."""

        try:
            logger.info("Запуск бота...")

            await db.connect()
            logger.info("Подключение к базе данных установлено")

            await self.set_commands()

            await self.dp.start_polling(self.bot)

        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            raise

    async def stop(self):
        """Остановка бота."""

        logger.info("Остановка бота...")
        await db.disconnect()
        logger.info("Соединение с базой данных закрыто")


async def main():
    """Основная функция для запуска бота."""
    bot = VideoStatsBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
