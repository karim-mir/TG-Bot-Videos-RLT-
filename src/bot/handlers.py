"""
Обработчики команд Telegram бота.
"""
import re
from datetime import datetime, timedelta
from typing import Tuple, Optional
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from src.core.database import db

logger = logging.getLogger(__name__)
router = Router()


class VideoInfoState(StatesGroup):
    """Состояния для получения информации о видео."""

    waiting_for_video_id = State()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    welcome_text = """
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
• 358 видео
• 19 креаторов
• 35K+ записей статистики
    """
    await message.answer(welcome_text)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    help_text = """
<b>📖 Справка по командам:</b>

<b>Общая информация:</b>
/stats - Общая статистика системы
  └ Показывает общее количество видео, креаторов, снапшотов

<b>Топы и рейтинги:</b>
/top_videos [N] - Топ видео по просмотрам (по умолчанию 10)
/top_creators [N] - Топ креаторов (по умолчанию 5)

<b>Информация о видео:</b>
/video_info - Получить информацию о конкретном видео
  └ После команды введите ID видео

<b>Аналитика:</b>
/daily_growth [дней] - Рост просмотров за период (по умолчанию 7)

<b>Примеры использования:</b>
• <code>/top_videos 5</code> - топ-5 видео
• <code>/daily_growth 3</code> - рост за 3 дня
• <code>/video_info</code> - затем введите ID видео
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
            if limit > 20:
                limit = 20
                await message.answer("⚠️ Лимит ограничен 20 видео для удобства чтения.")

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
        "Пример: <code>fde42b07-37f...</code>"
    )
    await state.set_state(VideoInfoState.waiting_for_video_id)


@router.message(VideoInfoState.waiting_for_video_id)
async def cmd_video_info_process(message: Message, state: FSMContext):
    """Обработка введенного ID видео."""
    video_id = message.text.strip()

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
            WHERE v.id LIKE $1 || '%%'
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
            if days > 30:
                days = 30
                await message.answer("⚠️ Период ограничен 30 днями для удобства чтения.")

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


def parse_date(date_str: str) -> Optional[datetime]:
    """Парсит дату из русского текста."""
    try:
        date_str = date_str.strip().lower()

        # Русские названия месяцев (полные и сокращенные)
        months = {
            'января': 1, 'янв': 1, 'февраля': 2, 'фев': 2,
            'марта': 3, 'мар': 3, 'апреля': 4, 'апр': 4,
            'мая': 5, 'май': 5, 'июня': 6, 'июн': 6,
            'июля': 7, 'июл': 7, 'августа': 8, 'авг': 8,
            'сентября': 9, 'сен': 9, 'октября': 10, 'окт': 10,
            'ноября': 11, 'ноя': 11, 'декабря': 12, 'дек': 12
        }

        # Пробуем распарсить диапазон дат
        range_pattern = r'с\s+(\d{1,2})\s+по\s+(\d{1,2})\s+(\w+)\s+(\d{4})'
        range_match = re.search(range_pattern, date_str)
        if range_match:
            day_from, day_to, month_ru, year = range_match.groups()
            month = months.get(month_ru)
            if month:
                date_from = datetime(int(year), month, int(day_from))
                date_to = datetime(int(year), month, int(day_to))
                return (date_from, date_to)

        # Пробуем распарсить одиночную дату
        # Паттерн для "1 ноября 2025" или "1 ноября"
        date_pattern = r'(\d{1,2})\s+(\w+)(?:\s+(\d{4}))?'
        match = re.search(date_pattern, date_str)
        if match:
            day = int(match.group(1))
            month_ru = match.group(2)
            month = months.get(month_ru)
            if month:
                year = int(match.group(3)) if match.group(3) else datetime.now().year
                return datetime(year, month, day)

        return None
    except Exception:
        return None


def parse_natural_query(query: str) -> Tuple[Optional[str], Optional[dict]]:
    """Парсит естественный запрос и возвращает SQL и параметры."""
    query = query.lower().strip()

    # Удаляем знаки вопроса в конце
    query = query.rstrip('?')

    # 1. "Сколько видео опубликовал/вышло у креатора с id X в период с Y по Z?"
    # Более гибкий паттерн для различных формулировок
    patterns_creator_dates = [
        # Паттерн для текущего запроса
        r'сколько видео (?:опубликовал|вышло у|у) креатор(?:а)? (?:с )?id\s+([a-f0-9\-]+)\s+(?:в период )?с\s+(.+?)\s+по\s+(.+?)(?:\s+включительно)?',
        r'сколько видео у креатора (?:с )?id\s+([a-f0-9\-]+)\s+вышло с\s+(.+?)\s+по\s+(.+?)(?:\s+включительно)?',
        r'креатор(?:а)? (?:с )?id\s+([a-f0-9\-]+).*с\s+(.+?)\s+по\s+(.+?)(?:\s+включительно)?.*сколько видео',
    ]

    for pattern in patterns_creator_dates:
        match = re.search(pattern, query, re.DOTALL)
        if match:
            creator_id = match.group(1).strip()
            date_from_str = match.group(2).strip()
            date_to_str = match.group(3).strip()

            # Логируем распарсенные даты
            print(f"Распарсенные даты: from='{date_from_str}', to='{date_to_str}'")

            date_from = parse_date(date_from_str)
            date_to = parse_date(date_to_str)

            if date_from and date_to:
                sql = """
                    SELECT COUNT(*) 
                    FROM videos 
                    WHERE creator_id = $1 
                    AND DATE(video_created_at) BETWEEN $2 AND $3
                """
                return sql, {
                    'creator_id': creator_id,
                    'date_from': date_from.date(),
                    'date_to': date_to.date()
                }
            else:
                print(f"Не удалось распарсить даты: from={date_from}, to={date_to}")

    # 2. "Сколько видео у креатора с id X набрали больше Y просмотров?"
    pattern_creator_views = r'сколько видео (?:у|у креатора с id|опубликовал креатор с id)\s+([a-f0-9\-]+)\s+(?:набрали|набрало) больше\s+(\d[\d\s,]*)\s+просмотров'
    match = re.search(pattern_creator_views, query)
    if match:
        creator_id = match.group(1).strip()
        views_str = match.group(2).replace(' ', '').replace(',', '')
        try:
            views = int(views_str)
            sql = """
                SELECT COUNT(*) 
                FROM videos 
                WHERE creator_id = $1 
                AND views_count > $2
            """
            return sql, {'creator_id': creator_id, 'views': views}
        except:
            pass

    # 3. "Сколько всего видео есть в системе?"
    if any(phrase in query for phrase in
           ["сколько всего видео", "сколько видео есть в системе", "сколько видео в системе"]):
        return "SELECT COUNT(*) FROM videos", {}

    # 4. "Сколько видео набрало больше X просмотров?"
    if "сколько видео" in query and "больше" in query and "просмотров" in query:
        # Ищем числа в запросе
        match = re.search(r'больше\s+(\d[\d\s,]*)\s+просмотров', query)
        if match:
            views_str = match.group(1).replace(' ', '').replace(',', '')
            try:
                views = int(views_str)
                return "SELECT COUNT(*) FROM videos WHERE views_count > $1", {'views': views}
            except:
                pass

    # 5. "Сколько разных креаторов?"
    if "сколько разных креаторов" in query or "сколько различных креаторов" in query:
        return "SELECT COUNT(DISTINCT creator_id) FROM videos", {}

    # 6. "На сколько просмотров в сумме выросли все видео [дата]?"
    patterns_growth = [
        r'на сколько просмотров.*выросли все видео\s+(.+)',
        r'на сколько просмотров в сумме выросли все видео\s+(.+)',
        r'суммарный рост просмотров всех видео\s+(.+)'
    ]

    for pattern in patterns_growth:
        match = re.search(pattern, query)
        if match:
            date_str = match.group(1).strip()
            date = parse_date(date_str)
            if isinstance(date, tuple):
                # Диапазон дат
                date_from, date_to = date
                sql = """
                    SELECT COALESCE(SUM(delta_views_count), 0) 
                    FROM video_snapshots 
                    WHERE DATE(created_at) BETWEEN $1 AND $2
                """
                return sql, {'date_from': date_from.date(), 'date_to': date_to.date()}
            elif date:
                # Одна дата
                sql = "SELECT COALESCE(SUM(delta_views_count), 0) FROM video_snapshots WHERE DATE(created_at) = $1"
                return sql, {'date': date.date()}

    # 7. "Сколько разных видео получали новые просмотры [дата]?"
    if "сколько разных видео получали новые просмотры" in query:
        # Извлекаем дату после этой фразы
        start_idx = query.find("получали новые просмотры") + len("получали новые просмотры")
        date_str = query[start_idx:].strip()
        date = parse_date(date_str)
        if date:
            sql = "SELECT COUNT(DISTINCT video_id) FROM video_snapshots WHERE DATE(created_at) = $1 AND delta_views_count > 0"
            return sql, {'date': date.date()}

    # 8. Общий паттерн для креатора без условий по просмотрам
    match = re.search(r'креатор(?:а)? (?:с )?id\s+([a-f0-9\-]+)', query)
    if match and "сколько видео" in query:
        creator_id = match.group(1).strip()

        # Без дополнительных условий
        sql = "SELECT COUNT(*) FROM videos WHERE creator_id = $1"
        return sql, {'creator_id': creator_id}

    return None, None


@router.message(F.text & ~F.text.startswith('/'))
async def handle_natural_query(message: Message):
    """Обработчик естественных запросов на русском языке."""
    query = message.text.strip()

    logger.info(f"Обрабатываем естественный запрос: {query}")

    try:
        sql, params = parse_natural_query(query)

        if not sql:
            await message.answer(
                "🤔 Я не понял ваш запрос. Попробуйте сформулировать иначе."
            )
            return

        # Логируем SQL и параметры
        logger.info(f"SQL: {sql}")
        logger.info(f"Params: {params}")

        # Выполняем запрос
        if params:
            param_values = list(params.values())
            result = await db.execute_scalar(sql, *param_values)
        else:
            result = await db.execute_scalar(sql)

        logger.info(f"Результат запроса: {result}")

        if result is None:
            result = 0

        # ФОРМАТИРУЕМ ОТВЕТ: ТОЛЬКО ЧИСЛО БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА
        response = str(int(result)) if isinstance(result, (int, float)) and (
                    isinstance(result, int) or result.is_integer()) else str(result)

        # Отправляем ТОЛЬКО число
        await message.answer(response)

    except Exception as e:
        logger.error(f"Ошибка при обработке запроса '{query}': {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке запроса."
        )


@router.message(F.text.startswith('/'))
async def handle_unknown_command(message: Message):
    """Обработчик неизвестных команд."""
    known_commands = [
        '/start', '/help', '/stats', '/top_videos',
        '/top_creators', '/video_info', '/daily_growth'
    ]

    if message.text.split()[0] not in known_commands:
        await message.answer(
            "🤔 Неизвестная команда.\n"
            "Используйте /help чтобы увидеть список доступных команд.\n\n"
            "Или задайте вопрос на естественном языке, например:\n"
            "• Сколько всего видео в системе?\n"
            "• Сколько видео набрало больше 1000 просмотров?"
        )
