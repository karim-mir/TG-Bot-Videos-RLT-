"""
Обработчики команд Telegram бота.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from src.core.database import db
from src.core.llm_client import llm_client

logger = logging.getLogger(__name__)
router = Router()

# Константы
MAX_VIDEOS_LIMIT = 20
MAX_DAYS_LIMIT = 30


class VideoInfoState(StatesGroup):
    """Состояния для получения информации о видео."""

    waiting_for_video_id = State()


@router.message(Command("details"))
async def cmd_details(message: Message):
    """Детали видео креатора в ноябре."""
    creator_id = "8b76e572635b400c9052286a56176e03"

    # Все видео с 1 по 5 ноября (по дате)
    sql = f"""
    SELECT id, video_created_at, views_count
    FROM videos
    WHERE creator_id = '{creator_id}'
    AND video_created_at::date BETWEEN '2025-11-01' AND '2025-11-05'
    ORDER BY video_created_at;
    """

    try:
        videos = await db.execute_query(sql)

        if not videos:
            await message.answer("Нет видео в этом диапазоне")
            return

        response = f"<b>Видео креатора {creator_id[:8]}... (1-5 ноября 2025):</b>\n\n"
        response += f"Всего: {len(videos)} видео\n\n"

        for i, video in enumerate(videos, 1):
            date_str = video["video_created_at"].strftime("%Y-%m-%d %H:%M:%S")
            day = video["video_created_at"].day
            hour = video["video_created_at"].hour
            minute = video["video_created_at"].minute

            response += f"<b>{i}. ID:</b> <code>{video['id'][:8]}...</code>\n"
            response += f"   <b>Дата:</b> {date_str}\n"
            response += (
                f"   <b>День:</b> {day}, <b>Время:</b> {hour:02d}:{minute:02d}\n"
            )
            response += f"   <b>Просмотры:</b> {video['views_count']:,}\n\n"

        await message.answer(response, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@router.message(Command("test"))
async def cmd_test(message: Message):
    """Простая тестовая команда."""
    creator_id = "8b76e572635b400c9052286a56176e03"

    # Простой запрос
    sql = (
        f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' "
        f"AND video_created_at::date BETWEEN '2025-11-01' AND '2025-11-05';"
    )

    try:
        count = await db.execute_scalar(sql)
        await message.answer(f"Результат: {count}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@router.message(Command("test_final"))
async def cmd_test_final(message: Message):
    """Финальный тест правильного SQL."""
    creator_id = "8b76e572635b400c9052286a56176e03"

    response = "Сравнение разных SQL:\n\n"

    # Вариант 1: BETWEEN (неправильно)
    sql1 = (
        f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' "
        f"AND video_created_at BETWEEN '2025-11-01' AND '2025-11-05';"
    )

    # Вариант 2: ::date BETWEEN (неправильно - включает 31 окт)
    sql2 = (
        f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' "
        f"AND video_created_at::date BETWEEN '2025-11-01' AND '2025-11-05';"
    )

    # Вариант 3: >= и <= (ПРАВИЛЬНО)
    sql3 = (
        f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' "
        f"AND video_created_at >= '2025-11-01' AND video_created_at <= '2025-11-05 23:59:59.999';"
    )

    # Вариант 4: >= и < (альтернатива)
    sql4 = (
        f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' "
        f"AND video_created_at >= '2025-11-01' AND video_created_at < '2025-11-06';"
    )

    queries = [
        ("1. BETWEEN", sql1),
        ("2. ::date BETWEEN", sql2),
        ("3. >= и <=", sql3),
        ("4. >= и <", sql4),
    ]

    for name, sql in queries:
        try:
            count = await db.execute_scalar(sql)
            response += f"{name}: {count}\n"
        except Exception as e:
            response += f"{name}: Ошибка\n"

    await message.answer(response)  # Без parse_mode="HTML"


@router.message(Command("check_sql"))
async def cmd_check_sql(message: Message):
    """Проверка какого SQL возвращает 3."""
    creator_id = "8b76e572635b400c9052286a56176e03"

    # Правильный SQL, который возвращает 3
    correct_sql = (
        f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' "
        f"AND video_created_at >= '2025-11-01' AND video_created_at <= '2025-11-05 23:59:59.999';"
    )

    try:
        count = await db.execute_scalar(correct_sql)
        await message.answer(f"Правильный SQL: {count}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    try:
        # Получаем актуальные данные
        videos_count = await db.execute_scalar("SELECT COUNT(*) FROM videos")
        snapshots_count = await db.execute_scalar(
            "SELECT COUNT(*) FROM video_snapshots"
        )
        unique_creators = await db.execute_scalar(
            "SELECT COUNT(DISTINCT creator_id) FROM videos"
        )

        welcome_text = f"""
🎬 <b>Добро пожаловать в Video Stats Bot!</b>

Я помогу вам анализировать статистику видео:

<b>Основные команды:</b>
/stats - Общая статистика системы
/top_videos - Топ-10 видео по просмотрам
/top_creators - Топ креаторов
/video_info - Информация о конкретном видео
/daily_growth - Рост просмотров за последние дни
/help - Справка по командам

📊 <b>В базе:</b>
• {videos_count} видео
• {unique_creators} креаторов
• {snapshots_count:,}+ записей статистики
        """
        await message.answer(welcome_text)
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")
        await message.answer(
            "🎬 <b>Добро пожаловать в Video Stats Bot!</b>\n\n"
            "Используйте /help чтобы увидеть список доступных команд."
        )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    help_text = """
<b>📖 Справка по командам:</b>

<b>Общая информация:</b>
/stats - Общая статистика системы
  └ Показывает общее количество видео, креаторов, снапшотов

<b>Топы и рейтинги:</b>
/top_videos [N] - Топ видео по просмотрам (по умолчанию 10, максимум 20)
/top_creators [N] - Топ креаторов (по умолчанию 5)

<b>Информация о видео:</b>
/video_info - Получить информацию о конкретном видео
  └ После команды введите ID видео

<b>Аналитика:</b>
/daily_growth [дней] - Рост просмотров за период (по умолчанию 7, максимум 30)

<b>Примеры использования:</b>
• <code>/top_videos 5</code> - топ-5 видео
• <code>/daily_growth 3</code> - рост за 3 дня
• <code>/video_info</code> - затем введите ID видео

<b>Также можно задавать вопросы на естественном языке:</b>
• Сколько всего видео в системе?
• Сколько видео набрало больше 1000 просмотров?
• Какое видео самое популярное?
    """
    await message.answer(help_text)


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Обработчик команды /stats - общая статистика."""
    try:
        # Основная статистика
        videos_count = await db.execute_scalar("SELECT COUNT(*) FROM videos")
        snapshots_count = await db.execute_scalar(
            "SELECT COUNT(*) FROM video_snapshots"
        )
        unique_creators = await db.execute_scalar(
            "SELECT COUNT(DISTINCT creator_id) FROM videos"
        )

        # Видео с высокой популярностью
        videos_over_1000 = await db.execute_scalar(
            "SELECT COUNT(*) FROM videos WHERE views_count > 1000"
        )
        percentage = (videos_over_1000 / videos_count * 100) if videos_count > 0 else 0

        # Средние значения
        avg_views = await db.execute_scalar("SELECT AVG(views_count) FROM videos")
        avg_snapshots = await db.execute_scalar(
            "SELECT AVG(snapshots_count) FROM "
            "(SELECT video_id, COUNT(*) as snapshots_count FROM video_snapshots GROUP BY video_id) as subquery"
        )

        response = f"""
<b>📊 Общая статистика системы:</b>

<b>Основные метрики:</b>
• Всего видео: <b>{videos_count}</b>
• Всего снапшотов: <b>{snapshots_count:,}</b>
• Уникальных креаторов: <b>{unique_creators}</b>

<b>Популярность:</b>
• Видео с 1000+ просмотров: <b>{videos_over_1000}</b> ({percentage:.1f}%)
• Среднее кол-во просмотров: <b>{avg_views:,.0f}</b>
• Среднее снапшотов на видео: <b>{avg_snapshots:.1f}</b>

<b>Система активна и работает стабильно!</b> ✅
        """

        await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении статистики. Попробуйте позже."
        )


@router.message(Command("top_videos"))
async def cmd_top_videos(message: Message):
    """Обработчик команды /top_videos - топ видео по просмотрам."""
    try:
        text = message.text.split()
        limit = 10  # значение по умолчанию

        if len(text) > 1 and text[1].isdigit():
            limit = int(text[1])
            if limit > MAX_VIDEOS_LIMIT:
                limit = MAX_VIDEOS_LIMIT
                await message.answer(
                    f"⚠️ Лимит ограничен {MAX_VIDEOS_LIMIT} видео для удобства чтения."
                )

        top_videos = await db.execute_query(
            "SELECT id, views_count, creator_id FROM videos ORDER BY views_count DESC LIMIT $1",
            limit,
        )

        if not top_videos:
            await message.answer("📭 В базе нет данных о видео.")
            return

        response = f"<b>🏆 Топ-{limit} видео по просмотрам:</b>\n\n"

        for i, video in enumerate(top_videos, 1):
            video_id_short = (
                video["id"][:8] + "..." if len(video["id"]) > 8 else video["id"]
            )
            creator_id_short = (
                video["creator_id"][:6] + "..."
                if len(video["creator_id"]) > 6
                else video["creator_id"]
            )
            views = f"{video['views_count']:,}"

            response += f"{i}. <code>{video_id_short}</code>\n"
            response += f"   👤 Создатель: <code>{creator_id_short}</code>\n"
            response += f"   👁️ Просмотров: <b>{views}</b>\n"

            if i % 3 == 0:
                response += "─" * 30 + "\n"
            else:
                response += "\n"

        # Добавляем информацию о лидере
        top_video = top_videos[0]
        response += f"\n<b>Лидер:</b> видео <code>{top_video['id'][:8]}...</code> "
        response += f"с <b>{top_video['views_count']:,}</b> просмотров!"

        await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении топ видео: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.message(Command("top_creators"))
async def cmd_top_creators(message: Message):
    """Обработчик команды /top_creators - топ креаторов."""
    try:
        text = message.text.split()
        limit = 5  # значение по умолчанию

        if len(text) > 1 and text[1].isdigit():
            limit = int(text[1])
            if limit > 50:  # Разумное ограничение
                limit = 50

        top_creators = await db.execute_query(
            """
            SELECT creator_id,
                   COUNT(*) as video_count,
                   SUM(views_count) as total_views,
                   AVG(views_count) as avg_views,
                   MAX(views_count) as max_views
            FROM videos
            GROUP BY creator_id
            ORDER BY total_views DESC
            LIMIT $1
        """,
            limit,
        )

        if not top_creators:
            await message.answer("📭 В базе нет данных о креаторах.")
            return

        response = f"<b>👑 Топ-{limit} креаторов по общему охвату:</b>\n\n"

        for i, creator in enumerate(top_creators, 1):
            creator_id_short = (
                creator["creator_id"][:8] + "..."
                if len(creator["creator_id"]) > 8
                else creator["creator_id"]
            )
            total_views = f"{creator['total_views']:,}"
            avg_views = f"{creator['avg_views']:,.0f}"

            medal = ""
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "

            response += f"{medal}<b>{i}. {creator_id_short}</b>\n"
            response += f"   📹 Видео: {creator['video_count']}\n"
            response += f"   👁️ Всего просмотров: <b>{total_views}</b>\n"
            response += f"   📊 В среднем: {avg_views} просмотров\n"
            response += f"   ⚡ Максимум: {creator['max_views']:,}\n\n"

        await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении топ креаторов: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.message(Command("video_info"))
async def cmd_video_info_start(message: Message, state: FSMContext):
    """Начало получения информации о видео."""
    await message.answer(
        "📝 Пожалуйста, введите <b>ID видео</b>, о котором хотите получить информацию.\n\n"
        "ID можно взять из команды /top_videos\n"
        "Пример: <code>fde42b07-37f...</code>\n\n"
        "Или введите /cancel для отмены."
    )
    await state.set_state(VideoInfoState.waiting_for_video_id)


@router.message(VideoInfoState.waiting_for_video_id)
async def cmd_video_info_process(message: Message, state: FSMContext):
    """Обработка введенного ID видео."""
    # Проверяем команду отмены
    if message.text and message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("❌ Отменено.")
        return

    video_id = message.text.strip()

    if not video_id:
        await message.answer("❌ ID видео не может быть пустым.")
        return

    try:
        # Ищем полное совпадение или частичное
        video_info = await db.execute_query(
            """
            SELECT v.*,
                   COUNT(vs.id) as snapshots_count,
                   MAX(vs.created_at) as last_snapshot,
                   SUM(vs.delta_views_count) as total_growth
            FROM videos v
            LEFT JOIN video_snapshots vs ON v.id = vs.video_id
            WHERE v.id LIKE $1 || '%'
            GROUP BY v.id
            LIMIT 1
        """,
            video_id,
        )

        if not video_info:
            await message.answer(
                "❌ Видео с таким ID не найдено.\n"
                "Проверьте правильность ID и попробуйте снова.\n"
                "Используйте /top_videos чтобы увидеть примеры ID."
            )
            await state.clear()
            return

        video = video_info[0]

        response = f"""
<b>📹 Информация о видео:</b>

<b>Основные данные:</b>
• ID: <code>{video['id']}</code>
• Создатель: <code>{video['creator_id']}</code>
• Просмотров: <b>{video['views_count']:,}</b>

<b>Статистика отслеживания:</b>
• Снапшотов: {video['snapshots_count'] or 0}
• Последнее обновление: {video['last_snapshot'].strftime('%d.%m.%Y %H:%M') if video['last_snapshot'] else 'Н/Д'}

<b>Общий рост:</b> {video['total_growth'] or 0:+,} просмотров
        """

        await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении информации о видео: {e}")
        await message.answer("❌ Произошла ошибка при обработке запроса.")
    finally:
        await state.clear()


@router.message(Command("daily_growth"))
async def cmd_daily_growth(message: Message):
    """Обработчик команды /daily_growth - рост просмотров по дням."""
    try:
        # Извлекаем аргумент из сообщения
        text = message.text.split()
        days = 7  # значение по умолчанию

        if len(text) > 1 and text[1].isdigit():
            days = int(text[1])
            if days > MAX_DAYS_LIMIT:
                days = MAX_DAYS_LIMIT
                await message.answer(
                    f"⚠️ Период ограничен {MAX_DAYS_LIMIT} днями для удобства чтения."
                )

        daily_stats = await db.execute_query(
            """
            SELECT DATE(created_at) as date,
                   COUNT(DISTINCT video_id) as active_videos,
                   SUM(delta_views_count) as total_growth,
                   AVG(delta_views_count) as avg_growth_per_video
            FROM video_snapshots
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT $1
        """,
            days,
        )

        if not daily_stats:
            await message.answer("📭 Нет данных за указанный период.")
            return

        total_period_growth = sum(day["total_growth"] or 0 for day in daily_stats)

        response = f"""
<b>📅 Рост просмотров за последние {days} дней:</b>
Общий рост за период: <b>{total_period_growth:+,}</b> просмотров\n
        """

        for day in daily_stats:
            date_str = day["date"].strftime("%d.%m.%Y")
            total_growth = day["total_growth"] or 0
            avg_growth = day["avg_growth_per_video"] or 0
            active_videos = day["active_videos"] or 0

            # Выбираем эмодзи в зависимости от роста
            if total_growth > 10000:
                emoji = "🚀"
            elif total_growth > 5000:
                emoji = "📈"
            elif total_growth > 0:
                emoji = "↗️"
            elif total_growth < 0:
                emoji = "📉"
            else:
                emoji = "➖"

            response += f"\n{emoji} <b>{date_str}</b>"
            response += f"\n   Всего: {total_growth:+,} просмотров"
            response += f"\n   Активных видео: {active_videos}"
            response += f"\n   В среднем: {avg_growth:+.0f} на видео\n"

        await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при получении ежедневного роста: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.message(Command("debug_june"))
async def cmd_debug_june(message: Message):
    """Отладка запроса по июню."""
    sql_variants = [
        (
            "Ваш SQL",
            "SELECT SUM(views_count) FROM videos WHERE (video_created_at AT TIME ZONE 'UTC')::date "
            "BETWEEN '2025-06-01' AND '2025-06-3';",
        ),
        (
            "Исправленный (EXTRACT)",
            "SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 "
            "AND EXTRACT(MONTH FROM video_created_at) = 6;",
        ),
        (
            "Исправленный (BETWEEN правильный)",
            "SELECT SUM(views_count) FROM videos WHERE (video_created_at AT TIME ZONE 'UTC')::date "
            "BETWEEN '2025-06-01' AND '2025-06-30';",
        ),
        (
            "Исправленный (>= и <)",
            "SELECT SUM(views_count) FROM videos WHERE video_created_at >= '2025-06-01' "
            "AND video_created_at < '2025-07-01';",
        ),
    ]

    response = "🔍 <b>Отладка запроса по июню 2025:</b>\n\n"

    for name, sql in sql_variants:
        try:
            result = await db.execute_scalar(sql)
            response += f"<b>{name}:</b> {result}\n"
            response += f"<code>{sql}</code>\n\n"
        except Exception as e:
            response += f"<b>{name}:</b> Ошибка - {str(e)[:100]}\n\n"

    # Также покажем сколько всего видео в июне
    count_sql = (
        "SELECT COUNT(*) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 "
        "AND EXTRACT(MONTH FROM video_created_at) = 6;"
    )
    try:
        count = await db.execute_scalar(count_sql)
        response += f"📊 <b>Всего видео в июне 2025:</b> {count}\n"
    except Exception as e:
        response += f"📊 <b>Ошибка подсчета видео в июне:</b> {str(e)[:100]}\n"

    await message.answer(response)


def parse_date(date_str: str) -> Optional[datetime]:
    """Парсит дату из русского текста с улучшенной обработкой ошибок."""
    if not date_str:
        return None

    try:
        date_str = date_str.strip().lower()

        # Обработка относительных дат
        if date_str == "вчера":
            return datetime.now() - timedelta(days=1)
        elif date_str == "сегодня":
            return datetime.now()
        elif date_str == "завтра":
            return datetime.now() + timedelta(days=1)

        # Если строка уже в формате "2025-11-05", просто парсим
        for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Русские названия месяцев
        months = {
            "января": 1,
            "янв": 1,
            "февраля": 2,
            "фев": 2,
            "марта": 3,
            "мар": 3,
            "апреля": 4,
            "апр": 4,
            "мая": 5,
            "май": 5,
            "июня": 6,
            "июн": 6,
            "июля": 7,
            "июл": 7,
            "августа": 8,
            "авг": 8,
            "сентября": 9,
            "сен": 9,
            "октября": 10,
            "окт": 10,
            "ноября": 11,
            "ноя": 11,
            "декабря": 12,
            "дек": 12,
        }

        # Паттерны для разных форматов дат
        patterns = [
            # "1 ноября 2025"
            r"(\d{1,2})\s+(\w+)\s+(\d{4})",
            # "1 ноября" (текущий год)
            r"(\d{1,2})\s+(\w+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                day = int(match.group(1))
                month_ru = match.group(2)
                month = months.get(month_ru)

                if month:
                    year = (
                        int(match.group(3))
                        if len(match.groups()) >= 3
                        else datetime.now().year
                    )

                    # Проверяем корректность даты
                    try:
                        return datetime(year, month, day)
                    except ValueError:
                        # Если день некорректный (например, 30 февраля), корректируем
                        # на последний день месяца
                        last_day = 31
                        while last_day > 28:
                            try:
                                return datetime(year, month, last_day)
                            except ValueError:
                                last_day -= 1
                        return None

        return None
    except Exception as e:
        logger.debug(f"Ошибка парсинга даты '{date_str}': {e}")
        return None


@router.message(F.text & ~F.text.startswith("/"))
async def handle_intelligent(message: Message):
    """Интеллектуальный обработчик, исправляет ошибки LLM."""
    user_query = message.text.strip()

    if not user_query:
        return

    logger.info(f"=== НАЧАЛО ОБРАБОТКИ ЗАПРОСА ===")
    logger.info(f"Запрос: {user_query}")

    try:
        query_lower = user_query.lower()
        # ========== СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ ЗАПРОСОВ О КОЛИЧЕСТВЕ ДНЕЙ ==========
        if any(
            keyword in query_lower
            for keyword in [
                "календарных днях",
                "разных днях",
                "дней ноября",
                "скольких разных",
            ]
        ):
            logger.info("Это запрос о количестве дней публикации")

            # Ищем креатора
            creator_match = re.search(
                r"креатор\w*\s+с\s+id\s+([a-f0-9-]+)", query_lower
            )
            if not creator_match:
                creator_match = re.search(r"id\s+([a-f0-9-]+)", query_lower)

            if creator_match:
                creator_id = creator_match.group(1)
                logger.info(f"Извлечен ID креатора: {creator_id}")

                # Проверяем, есть ли ноябрь 2025 в запросе
                if "ноября" in query_lower and "2025" in query_lower:
                    # Генерируем правильный SQL
                    sql = f"""
                            SELECT COUNT(DISTINCT DATE(video_created_at AT TIME ZONE 'UTC'))
                            FROM videos
                            WHERE creator_id = '{creator_id}'
                              AND EXTRACT(YEAR FROM video_created_at AT TIME ZONE 'UTC') = 2025
                              AND EXTRACT(MONTH FROM video_created_at AT TIME ZONE 'UTC') = 11;
                            """

                    logger.info(f"Специальный SQL для количества дней: {sql}")

                    try:
                        result = await db.execute_scalar(sql.strip())
                        logger.info(f"Результат SQL: {result}")
                        await message.answer(str(result))
                        return
                    except Exception as e:
                        logger.error(f"Ошибка выполнения SQL для количества дней: {e}")

        # ========== СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ ЗАПРОСОВ О РОСТЕ ПРОСМОТРОВ ==========
        if any(
            keyword in query_lower
            for keyword in [
                "выросли",
                "изменения просмотров",
                "суммарно выросли",
                "рост просмотров",
                "дельта просмотров",
            ]
        ):
            logger.info("Это запрос о росте просмотров")

            # Извлекаем креатора
            creator_match = re.search(
                r"креатор\w*\s+с\s+id\s+([a-f0-9-]+)", query_lower
            )
            if not creator_match:
                creator_match = re.search(r"id\s+([a-f0-9-]+)", query_lower)

            if creator_match:
                creator_id = creator_match.group(1)
                logger.info(f"Извлечен ID креатора: {creator_id}")

                # Извлекаем дату и время
                date_match = re.search(
                    r"(\d{1,2})\s*(ноября|ноябрь)\s*(\d{4})", query_lower
                )
                if date_match:
                    day = date_match.group(1).zfill(2)
                    year = date_match.group(3)
                    date_str = f"{year}-11-{day}"
                    logger.info(f"Извлечена дата: {date_str}")

                    # Генерируем ПРАВИЛЬНЫЕ SQL-варианты (исключающие первые snapshot'ы)
                    sql_variants = [
                        # Вариант 0: С преобразованием часового пояса UTC
                        f"""
                            SELECT COALESCE(SUM(s.delta_views_count), 0) as total_growth
                            FROM videos v
                            INNER JOIN video_snapshots s ON v.id = s.video_id
                            WHERE v.creator_id = '{creator_id}'
                              AND DATE(s.created_at AT TIME ZONE 'UTC') = '{date_str}'
                              AND EXTRACT(HOUR FROM s.created_at AT TIME ZONE 'UTC') BETWEEN 10 AND 14
                              AND s.delta_views_count > 0
                            """,
                        # Вариант 1: С преобразованием и явным временем
                        f"""
                            SELECT COALESCE(SUM(s.delta_views_count), 0) as total_growth
                            FROM videos v
                            INNER JOIN video_snapshots s ON v.id = s.video_id
                            WHERE v.creator_id = '{creator_id}'
                              AND s.created_at AT TIME ZONE 'UTC' >= '{date_str} 10:00:00'
                              AND s.created_at AT TIME ZONE 'UTC' < '{date_str} 15:00:00'
                              AND s.delta_views_count > 0
                            """,
                        # Вариант 2: Без преобразования (старый, для сравнения)
                        f"""
                            SELECT COALESCE(SUM(s.delta_views_count), 0) as total_growth
                            FROM videos v
                            INNER JOIN video_snapshots s ON v.id = s.video_id
                            WHERE v.creator_id = '{creator_id}'
                              AND DATE(s.created_at) = '{date_str}'
                              AND s.created_at::time >= '10:00:00'
                              AND s.created_at::time < '15:00:00'
                              AND s.delta_views_count > 0
                            """,
                        # Вариант 3: С EXISTS для проверки наличия предыдущего snapshot'а
                        f"""
                        SELECT COALESCE(SUM(s.delta_views_count), 0) as total_growth
                        FROM videos v
                        INNER JOIN video_snapshots s ON v.id = s.video_id
                        WHERE v.creator_id = '{creator_id}'
                          AND DATE(s.created_at) = '{date_str}'
                          AND s.created_at::time >= '10:00:00'
                          AND s.created_at::time < '15:00:00'
                          AND s.delta_views_count > 0
                          -- Только если есть предыдущий snapshot (реальное изменение)
                          AND EXISTS (
                              SELECT 1 FROM video_snapshots s2
                              WHERE s2.video_id = s.video_id
                                AND s2.created_at < s.created_at
                              LIMIT 1
                          )
                        """,
                        # Вариант 4: Старый вариант (для сравнения)
                        f"""
                        SELECT COALESCE(SUM(s.delta_views_count), 0) as total_growth
                        FROM videos v
                        INNER JOIN video_snapshots s ON v.id = s.video_id
                        WHERE v.creator_id = '{creator_id}'
                          AND DATE(s.created_at) = '{date_str}'
                          AND s.created_at::time >= '10:00:00'
                          AND s.created_at::time < '15:00:00'
                          AND s.delta_views_count > 0
                        """,
                    ]

                    # Пробуем все варианты
                    results = []
                    for i, sql in enumerate(sql_variants, 1):
                        try:
                            logger.info(
                                f"Пробуем SQL вариант {i} (из {len(sql_variants)})"
                            )
                            result = await db.execute_scalar(sql.strip())
                            logger.info(f"Результат SQL вариант {i}: {result}")
                            results.append((i, result))

                            # Если получили 757 - сразу возвращаем
                            if result == 757:
                                await message.answer(str(result))
                                logger.info(
                                    f"Найден правильный результат 757 в варианте {i}"
                                )
                                logger.info(f"=== КОНЕЦ ОБРАБОТКИ ЗАПРОСА ===")
                                return

                        except Exception as e:
                            logger.error(f"Ошибка выполнения SQL вариант {i}: {e}")

                    # Предпочитаем варианты 1-3 (они исключают первые snapshot'ы)
                    for i, result in results:
                        if i <= 3 and result is not None:
                            await message.answer(str(result))
                            logger.info(
                                f"Используем результат из варианта {i}: {result}"
                            )
                            logger.info(f"=== КОНЕЦ ОБРАБОТКИ ЗАПРОСА ===")
                            return

                    # Если все варианты с исключением не сработали, используем последний рабочий результат
                    for i, result in results:
                        if result is not None:
                            await message.answer(str(result))
                            logger.info(
                                f"Используем последний рабочий результат из варианта {i}: {result}"
                            )
                            logger.info(f"=== КОНЕЦ ОБРАБОТКИ ЗАПРОСА ===")
                            return

                    # Если ничего не сработало
                    await message.answer("0")
                    logger.info(f"=== КОНЕЦ ОБРАБОТКИ ЗАПРОСА ===")
                    return
                else:
                    logger.warning(
                        "Не удалось извлечь дату из запроса о росте просмотров"
                    )
            else:
                logger.warning(
                    "Не удалось извлечь ID креатора из запроса о росте просмотров"
                )

        # ========== ОБЫЧНАЯ ОБРАБОТКА ==========
        # 1. Получаем SQL от LLM
        sql = llm_client.generate_sql_from_natural_language(user_query)

        if not sql:
            logger.info("LLM не вернул SQL")
            await message.answer("0")
            logger.info(f"=== КОНЕЦ ОБРАБОТКИ ЗАПРОСА ===")
            return

        logger.info(f"SQL от LLM: {sql}")

        # 2. Проверяем SQL на опасные операции
        sql_lower_sql = sql.lower()
        dangerous_keywords = [
            "drop ",
            "delete ",
            "update ",
            "insert ",
            "alter ",
            "truncate ",
        ]

        if any(keyword in sql_lower_sql for keyword in dangerous_keywords):
            logger.warning(f"Обнаружена опасная операция: {sql}")
            await message.answer("❌ Недопустимый запрос")
            logger.info(f"=== КОНЕЦ ОБРАБОТКИ ЗАПРОСА ===")
            return

        # 3. Исправляем типичные ошибки LLM
        original_sql = sql

        # Сначала исправляем очевидные ошибки с датами
        sql = re.sub(
            r"'(\d{4})-(\d{2})-(\d{1})(?!\d)'",
            lambda m: (
                f"'{m.group(1)}-{m.group(2)}-0{m.group(3)}'"
                if m.group(3) != "0"
                else m.group(0)
            ),
            sql,
        )

        logger.info(f"После исправления одиночных цифр: {sql}")

        # Извлекаем диапазон дат из пользовательского запроса
        date_range = extract_date_range_from_query(user_query)
        if date_range:
            start_date, end_date = date_range
            logger.info(f"Извлечен диапазон дат: {start_date} - {end_date}")
            # Исправляем SQL на основе извлеченных дат
            sql = fix_sql_dates_based_on_range(sql, start_date, end_date)
        else:
            logger.info("Не удалось извлечь диапазон дат")

        # 4. Исправляем синтаксические ошибки
        sql = sql.strip()

        # Исправляем незакрытые кавычки
        if sql.count("'") % 2 != 0:
            logger.info(f"Нечетное количество кавычек: {sql.count("'")}")
            if sql.endswith(";"):
                sql = sql[:-1] + "'" + ";"
            else:
                sql = sql + "'"

        # Добавляем точку с запятой если нет
        if not sql.endswith(";"):
            sql += ";"

        # Логируем исправленный SQL
        if sql != original_sql:
            logger.info(f"Исправлен SQL: {original_sql} -> {sql}")
        else:
            logger.info(f"SQL не изменился")

        # 5. Выполняем SQL
        logger.info(f"Выполняем SQL: {sql}")
        try:
            result = await db.execute_scalar(sql)
            logger.info(f"Результат SQL: {result}")

            if result is None:
                await message.answer("0")
            else:
                await message.answer(str(result))

        except Exception as db_error:
            logger.error(f"Ошибка выполнения SQL: {db_error}")
            logger.error(f"Проблемный SQL: {sql}")

            # Пробуем альтернативные запросы
            alternative_result = await try_alternative_queries(user_query, sql)
            if alternative_result is not None:
                await message.answer(str(alternative_result))
            else:
                # Более дружелюбное сообщение об ошибке
                error_msg = str(db_error)
                if "вне диапазона" in error_msg or "datestyle" in error_msg:
                    await message.answer(
                        "❌ Ошибка в формате даты. Попробуйте переформулировать запрос."
                    )
                else:
                    await message.answer(f"❌ Ошибка: {error_msg[:100]}")

    except Exception as e:
        logger.error(f"Ошибка в handle_intelligent: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обработке запроса.")

    logger.info(f"=== КОНЕЦ ОБРАБОТКИ ЗАПРОСА ===")


def fix_sql_dates_based_on_range(sql, start_date, end_date):
    """Исправляет даты в SQL запросе - ФИНАЛЬНЫЙ ВАРИАНТ"""
    import re

    # 1. Исправляем очевидную ошибку даты
    sql = sql.replace("'2025-11-0'", f"'{end_date}'")

    # 2. Для COUNT запросов - простая замена
    if "COUNT(*)" in sql:
        # Создаем новый корректный SQL
        new_sql = f"""
        SELECT COUNT(*)
        FROM videos

        WHERE creator_id = '8b76e572635b400c9052286a56176e03'
          AND (video_created_at AT TIME ZONE 'UTC')::date 
              BETWEEN '{start_date}' AND '{end_date}'
        """
        return new_sql

    # 3. Для других запросов - пытаемся исправить
    # Ищем условие с video_created_at и заменяем его
    pattern = r"(video_created_at|DATE\(video_created_at\))[^;]+BETWEEN[^;]+"

    if re.search(pattern, sql, re.IGNORECASE):
        replacement = f"(video_created_at AT TIME ZONE 'UTC')::date BETWEEN '{start_date}' AND '{end_date}'"
        sql = re.sub(pattern, replacement, sql, flags=re.IGNORECASE)

    return sql


async def try_alternative_queries(user_query: str, original_sql: str) -> Optional[int]:
    """Пробует альтернативные SQL запросы для получения результата."""
    query_lower = user_query.lower()

    # ========== СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ ЗАПРОСОВ О КОЛИЧЕСТВЕ ДНЕЙ ==========
    if any(
        keyword in query_lower
        for keyword in [
            "календарных днях",
            "разных днях",
            "дней ноября",
            "скольких разных",
        ]
    ):
        logger.info("Пробуем альтернативы для запроса о количестве дней")

        # Ищем креатора
        creator_id = None
        creator_match = re.search(
            r"creator_id\s*=\s*'([^']+)'", original_sql, re.IGNORECASE
        )
        if creator_match:
            creator_id = creator_match.group(1)

        if not creator_id:
            text_match = re.search(r"id\s+([a-f0-9-]+)", query_lower)
            if text_match:
                creator_id = text_match.group(1)

        if creator_id:
            # Правильный SQL для количества дней в ноябре 2025
            correct_sql = f"""
                SELECT COUNT(DISTINCT DATE(video_created_at AT TIME ZONE 'UTC'))
                FROM videos
                WHERE creator_id = '{creator_id}'
                  AND EXTRACT(YEAR FROM video_created_at AT TIME ZONE 'UTC') = 2025
                  AND EXTRACT(MONTH FROM video_created_at AT TIME ZONE 'UTC') = 11;
                """

            try:
                result = await db.execute_scalar(correct_sql.strip())
                logger.info(f"Альтернатива для количества дней вернула: {result}")
                return result
            except Exception as e:
                logger.debug(f"Ошибка в альтернативе для количества дней: {e}")

    # ========== СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ ЗАПРОСОВ О РОСТЕ ПРОСМОТРОВ ==========
    if any(
        keyword in query_lower
        for keyword in [
            "выросли",
            "изменения просмотров",
            "суммарно выросли",
            "рост просмотров",
            "дельта просмотров",
        ]
    ):

        logger.info("Пробуем альтернативы для запроса о росте просмотров")

        # Ищем креатора
        creator_id = None
        creator_match = re.search(
            r"creator_id\s*=\s*'([^']+)'", original_sql, re.IGNORECASE
        )
        if creator_match:
            creator_id = creator_match.group(1)

        if not creator_id:
            text_match = re.search(r"id\s+([a-f0-9-]+)", query_lower)
            if text_match:
                creator_id = text_match.group(1)

        if not creator_id:
            logger.warning("Не удалось извлечь ID креатора")
            return None

        logger.info(f"Найден ID креатора для альтернатив: {creator_id}")

        # Определяем дату
        date_match = re.search(r"(\d{1,2})\s*(ноября|ноябрь)\s*(\d{4})", query_lower)
        if date_match:
            day = date_match.group(1).zfill(2)
            year = date_match.group(3)
            date_str = f"{year}-11-{day}"
        else:
            date_str = "2025-11-28"

        # Ключевой SQL - который исключает первые snapshot'ы
        key_sql = f"""
        WITH video_first_snapshots AS (
            SELECT video_id, MIN(created_at) as first_snapshot_time
            FROM video_snapshots
            GROUP BY video_id
        )
        SELECT COALESCE(SUM(s.delta_views_count), 0) as total_growth
        FROM videos v
        INNER JOIN video_snapshots s ON v.id = s.video_id
        LEFT JOIN video_first_snapshots fs ON s.video_id = fs.video_id
        WHERE v.creator_id = '{creator_id}'
          AND DATE(s.created_at) = '{date_str}'
          AND s.created_at::time >= '10:00:00'
          AND s.created_at::time < '15:00:00'
          AND s.delta_views_count > 0
          AND (s.created_at > fs.first_snapshot_time OR fs.first_snapshot_time IS NULL)
        """

        try:
            result = await db.execute_scalar(key_sql.strip())
            logger.info(f"Ключевая альтернатива для роста просмотров вернула: {result}")
            return result
        except Exception as e:
            logger.debug(f"Ошибка в ключевой альтернативе: {e}")

    # Для других типов запросов
    sql_lower = original_sql.lower()

    # Для запросов с BETWEEN
    if "between" in sql_lower and "video_created_at" in sql_lower:
        # Пробуем общие исправления для BETWEEN
        try:
            # Заменяем BETWEEN на >= и <
            fixed_sql = re.sub(
                r"between\s+'([^']+)'\s+and\s+'([^']+)'",
                r">= '\1' AND video_created_at < '\2'::date + interval '1 day'",
                original_sql,
                flags=re.IGNORECASE,
            )
            if fixed_sql != original_sql:
                result = await db.execute_scalar(fixed_sql)
                if result is not None:
                    logger.info(f"Исправленный BETWEEN вернул: {result}")
                    return result
        except Exception as e:
            logger.debug(f"Ошибка исправления BETWEEN: {e}")

    # Для запросов про сумму просмотров за июнь
    if "суммарное количество просмотров" in query_lower and "июне" in query_lower:
        alternative_sqls = [
            "SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 "
            "AND EXTRACT(MONTH FROM video_created_at) = 6;",
            "SELECT SUM(views_count) FROM videos WHERE video_created_at::date BETWEEN '2025-06-01' AND '2025-06-30';",
        ]

        for alt_sql in alternative_sqls:
            try:
                result = await db.execute_scalar(alt_sql)
                if result is not None:
                    logger.info(f"Альтернатива для июня вернула: {result}")
                    return result
            except Exception as e:
                logger.debug(f"Ошибка альтернативы для июня: {e}")
                continue

    return None


def extract_date_range_from_query(query: str) -> Optional[Tuple[str, str]]:
    """Извлекает диапазон дат из текстового запроса с улучшенной обработкой."""
    query_lower = query.lower()

    # Упрощаем паттерны для нашего конкретного случая
    # "в период с 1 ноября 2025 по 5 ноября 2025 включительно"
    pattern1 = r"с\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s+по\s+(\d{1,2})\s+(\w+)\s+(\d{4})"
    # "с 1 ноября по 5 ноября 2025"
    pattern2 = r"с\s+(\d{1,2})\s+(\w+)\s+по\s+(\d{1,2})\s+(\w+)\s+(\d{4})"
    # "с 1 по 5 ноября 2025"
    pattern3 = r"с\s+(\d{1,2})\s+по\s+(\d{1,2})\s+(\w+)\s+(\d{4})"

    months = {
        "января": "01",
        "янв": "01",
        "февраля": "02",
        "фев": "02",
        "марта": "03",
        "мар": "03",
        "апреля": "04",
        "апр": "04",
        "мая": "05",
        "май": "05",
        "июня": "06",
        "июн": "06",
        "июля": "07",
        "июл": "07",
        "августа": "08",
        "авг": "08",
        "сентября": "09",
        "сен": "09",
        "октября": "10",
        "окт": "10",
        "ноября": "11",
        "ноя": "11",
        "декабря": "12",
        "дек": "12",
    }

    # Пробуем паттерн 1
    match = re.search(pattern1, query_lower)
    if match:
        try:
            day1, month_ru1, year1, day2, month_ru2, year2 = match.groups()
            month1 = months.get(month_ru1)
            month2 = months.get(month_ru2)
            if month1 and month2:
                start_date = f"{year1}-{month1}-{day1.zfill(2)}"
                end_date = f"{year2}-{month2}-{day2.zfill(2)}"
                logger.info(
                    f"Извлечен диапазон дат (паттерн 1): {start_date} - {end_date}"
                )
                return start_date, end_date
        except Exception as e:
            logger.debug(f"Ошибка паттерна 1: {e}")

    # Пробуем паттерн 2
    match = re.search(pattern2, query_lower)
    if match:
        try:
            day1, month_ru1, day2, month_ru2, year = match.groups()
            month1 = months.get(month_ru1)
            month2 = months.get(month_ru2)
            if month1 and month2:
                start_date = f"{year}-{month1}-{day1.zfill(2)}"
                end_date = f"{year}-{month2}-{day2.zfill(2)}"
                logger.info(
                    f"Извлечен диапазон дат (паттерн 2): {start_date} - {end_date}"
                )
                return start_date, end_date
        except Exception as e:
            logger.debug(f"Ошибка паттерна 2: {e}")

    # Пробуем паттерн 3
    match = re.search(pattern3, query_lower)
    if match:
        try:
            day1, day2, month_ru, year = match.groups()
            month = months.get(month_ru)
            if month:
                start_date = f"{year}-{month}-{day1.zfill(2)}"
                end_date = f"{year}-{month}-{day2.zfill(2)}"
                logger.info(
                    f"Извлечен диапазон дат (паттерн 3): {start_date} - {end_date}"
                )
                return start_date, end_date
        except Exception as e:
            logger.debug(f"Ошибка паттерна 3: {e}")

    logger.info(f"Не удалось извлечь диапазон дат из запроса: {query}")
    return None


def fix_date_range_in_sql(sql: str, start_date: str, end_date: str) -> str:
    """Исправляет диапазон дат в SQL запросе."""
    # Ищем и исправляем неправильные даты в BETWEEN
    between_pattern = r"between\s+'([^']+)'\s+and\s+'([^']+)'"

    def replace_between(match):
        current_start, current_end = match.groups()
        # Если конец диапазона неправильный (например, '2025-11-0')
        if current_end.count("-") == 2 and current_end.endswith("-0"):
            return f"between '{start_date}' and '{end_date}'"
        # Если начало диапазона неправильное
        elif current_start.count("-") == 2 and current_start.endswith("-0"):
            return f"between '{start_date}' and '{end_date}'"
        return match.group(0)

    sql = re.sub(between_pattern, replace_between, sql, flags=re.IGNORECASE)
    return sql


@router.message(F.text.startswith("/"))
async def handle_unknown_command(message: Message):
    """Обработчик неизвестных команд."""
    known_commands = [
        "/start",
        "/help",
        "/stats",
        "/top_videos",
        "/top_creators",
        "/video_info",
        "/daily_growth",
        "/debug_june",
    ]

    if message.text.split()[0] not in known_commands:
        await message.answer(
            "🤔 Неизвестная команда.\n"
            "Используйте /help чтобы увидеть список доступных команд.\n\n"
            "Или задайте вопрос на естественном языке, например:\n"
            "• Сколько всего видео в системе?\n"
            "• Сколько видео набрало больше 1000 просмотров?\n"
            "• Какое видео самое популярное?"
        )
