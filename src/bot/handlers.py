"""
Обработчики команд Telegram бота.
"""
import re
import textwrap
from datetime import datetime, timedelta
from typing import Tuple, Optional
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from src.core.database import db
from src.core.llm_client import llm_client

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

        # Если строка уже в формате "2025-11-05", просто парсим
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except:
            pass

        # Русские названия месяцев (полные и сокращенные)
        months = {
            'января': 1, 'янв': 1, 'февраля': 2, 'фев': 2,
            'марта': 3, 'мар': 3, 'апреля': 4, 'апр': 4,
            'мая': 5, 'май': 5, 'июня': 6, 'июн': 6,
            'июля': 7, 'июл': 7, 'августа': 8, 'авг': 8,
            'сентября': 9, 'сен': 9, 'октября': 10, 'окт': 10,
            'ноября': 11, 'ноя': 11, 'декабря': 12, 'дек': 12
        }

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

        # Если строка - просто число, возвращаем None
        # (месяц и год будут добавлены позже из контекста)
        if date_str.isdigit():
            return None

        return None
    except Exception:
        return None


def parse_natural_query(query: str) -> Tuple[Optional[str], Optional[dict]]:
    """Парсит естественный запрос и возвращает SQL и параметры."""
    # Сначала пробуем простые правила (для частых запросов)
    query_lower = query.lower().strip().rstrip('?')

    # 1. Очень простые запросы (можно обработать без LLM)
    if "сколько всего видео" in query_lower and "систем" in query_lower:
        return "SELECT COUNT(*) FROM videos", {}

    if "сколько разных креаторов" in query_lower:
        return "SELECT COUNT(DISTINCT creator_id) FROM videos", {}

    # 2. Если есть LLM клиент - используем его
    if llm_client:
        try:
            # Получаем SQL от LLM
            sql = llm_client.generate_sql_from_natural_language(query)
            logger.info(f"LLM сгенерировал SQL: {sql}")

            # Извлекаем параметры из запроса (если есть)
            params = extract_params_from_query(query, sql)

            return sql, params

        except Exception as e:
            logger.error(f"Ошибка LLM: {e}")
            # Если LLM не сработал, продолжаем с обычными правилами

    # 3. Продолжаем с обычными правилами
    return parse_with_rules(query)


def extract_params_from_query(query: str, sql: str) -> dict:
    """Извлекает параметры из запроса пользователя."""
    params = {}
    query_lower = query.lower()

    # Ищем ID креатора
    id_match = re.search(r'id\s+([a-f0-9\-]+)', query_lower)
    if id_match:
        params['creator_id'] = id_match.group(1)

    # Ищем числа (просмотры, лайки и т.д.)
    number_match = re.search(r'больше\s+(\d[\d\s,]*)', query_lower)
    if number_match:
        number_str = number_match.group(1).replace(' ', '').replace(',', '')
        try:
            params['views'] = int(number_str)
        except:
            pass

    # Ищем даты (упрощенный вариант)
    date_match = re.search(
        r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',
        query_lower)
    if date_match:
        # Здесь нужно парсить дату через parse_date
        pass

    return params


def parse_with_rules(query: str) -> Tuple[Optional[str], Optional[dict]]:
    """Резервный парсер с правилами (когда LLM недоступен)."""
    query_lower = query.lower().strip().rstrip('?')

    # 1. "Сколько всего видео есть в системе?"
    if any(phrase in query_lower for phrase in ["сколько всего видео", "сколько видео есть в системе"]):
        return "SELECT COUNT(*) FROM videos", {}

    # 2. "Сколько видео набрало больше X просмотров?"
    if "сколько видео" in query_lower and "больше" in query_lower and "просмотров" in query_lower:
        match = re.search(r'больше\s+(\d[\d\s,]*)\s+просмотров', query_lower)
        if match:
            views_str = match.group(1).replace(' ', '').replace(',', '')
            try:
                views = int(views_str)
                return "SELECT COUNT(*) FROM videos WHERE views_count > $1", {'views': views}
            except:
                pass

    # 3. "Сколько разных креаторов?"
    if "сколько разных креаторов" in query_lower:
        return "SELECT COUNT(DISTINCT creator_id) FROM videos", {}

    # 4. "На сколько просмотров выросли все видео [дата]?"
    if "на сколько просмотров" in query_lower and "выросли все видео" in query_lower:
        date_match = re.search(r'выросли все видео\s+(.+)', query_lower)
        if date_match:
            date_str = date_match.group(1).strip()
            date = parse_date(date_str)
            if date:
                return "SELECT COALESCE(SUM(delta_views_count), 0) FROM video_snapshots WHERE DATE(created_at) = $1", {
                    'date': date.date()}

    # 5. "Сколько разных видео получали новые просмотры [дата]?"
    if "сколько разных видео получали новые просмотры" in query_lower:
        date_match = re.search(r'получали новые просмотры\s+(.+)', query_lower)
        if date_match:
            date_str = date_match.group(1).strip()
            date = parse_date(date_str)
            if date:
                return "SELECT COUNT(DISTINCT video_id) FROM video_snapshots WHERE DATE(created_at) = $1 AND delta_views_count > 0", {
                    'date': date.date()}

    # 6. "Сколько всего есть замеров статистики с отрицательными просмотрами?"
    if any(keyword in query_lower for keyword in ["замеров статистики", "отрицательными просмотрами"]):
        return "SELECT COUNT(*) FROM video_snapshots WHERE delta_views_count < 0", {}

    # 7. "Сколько видео у креатора с id ..."
    match = re.search(r'креатора с id\s+([a-f0-9\-]+)', query_lower)
    if match:
        creator_id = match.group(1).strip()

        # Проверяем диапазон дат
        if "с" in query_lower and "по" in query_lower:
            # Упрощенный вариант без точного парсинга дат
            return "SELECT COUNT(*) FROM videos WHERE creator_id = $1", {'creator_id': creator_id}

        return "SELECT COUNT(*) FROM videos WHERE creator_id = $1", {'creator_id': creator_id}

    return None, None


@router.message(F.text & ~F.text.startswith('/'))
async def handle_natural_query(message: Message):
    """Обработка естественного языка - ДОЛЖЕН БЫТЬ ПЕРВЫМ!"""
    user_query = message.text.strip()
    logger.info(f"Естественный запрос: {user_query}")

    # Проверяем, это команда или нет
    if user_query.startswith('/'):
        return  # Пропускаем, обработают другие хендлеры

    try:
        # Генерация SQL через LLM
        sql = llm_client.generate_sql_from_natural_language(user_query)

        if not sql:
            await message.answer("Не удалось сгенерировать запрос. Попробуйте сформулировать иначе.")
            return

        logger.info(f"LLM сгенерировал SQL: {sql}")

        # Исполнение SQL
        try:
            # Для COUNT запросов
            sql_upper = sql.upper().strip()

            if sql_upper.startswith('SELECT COUNT'):
                # COUNT запрос
                result = await db.execute_scalar(sql)
                await message.answer(f"Результат: {result}")

            elif sql_upper.startswith('SELECT'):
                # SELECT запрос (много строк)
                result = await db.execute_query(sql)
                if not result:
                    await message.answer("Данные не найдены.")
                    return

                # Форматируем результат
                response = "Результаты:\n"
                for row in result[:10]:
                    response += f"- {row}\n"

                if len(result) > 10:
                    response += f"\n... и еще {len(result) - 10} строк"

                await message.answer(response[:4000])

            else:
                # Другие запросы
                await db.execute(sql)
                await message.answer(f"Запрос выполнен: {sql[:100]}...")

        except Exception as e:
            logger.error(f"Ошибка выполнения SQL: {e}")
            await message.answer(f"Ошибка выполнения запроса: {str(e)[:100]}")

    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await message.answer("Произошла ошибка при обработке запроса.")


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
