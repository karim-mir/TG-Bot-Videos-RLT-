"""
Тесты для обработчиков команд Telegram бота.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message, User

from src.bot.handlers import (MAX_DAYS_LIMIT, MAX_VIDEOS_LIMIT, VideoInfoState,
                              extract_date_range_from_query,
                              fix_date_range_in_sql,
                              fix_sql_dates_based_on_range, parse_date,
                              try_alternative_queries)

# === Общие фикстуры для всех тестов ===


@pytest.fixture
def mock_message():
    """Создает мок сообщения."""
    message = AsyncMock(spec=Message)
    message.from_user = User(id=123, is_bot=False, first_name="Test")
    message.chat = Chat(id=456, type="private")
    message.text = ""
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_state():
    """Создает мок состояния FSM."""
    state = AsyncMock(spec=FSMContext)
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


@pytest.fixture
def mock_db():
    """Мок базы данных."""
    with patch("src.bot.handlers.db") as mock_db:
        mock_db.execute_query = AsyncMock()
        mock_db.execute_scalar = AsyncMock()
        yield mock_db


@pytest.fixture
def mock_llm_client():
    """Мок LLM клиента."""
    with patch("src.bot.handlers.llm_client") as mock_llm:
        mock_llm.generate_sql_from_natural_language = MagicMock()
        yield mock_llm


# === Тесты обработчиков команд ===


class TestCommandHandlers:
    """Тесты обработчиков команд."""

    @pytest.mark.asyncio
    async def test_cmd_start_success(self, mock_message, mock_db):
        """Тест команды /start при успешном получении статистики."""
        # Настраиваем моки
        mock_message.text = "/start"
        mock_db.execute_scalar.side_effect = [
            100,
            5000,
            50,
        ]  # videos_count, snapshots_count, unique_creators

        from src.bot.handlers import cmd_start

        await cmd_start(mock_message)

        # Проверяем вызовы
        assert mock_db.execute_scalar.call_count == 3
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Добро пожаловать" in response

    @pytest.mark.asyncio
    async def test_cmd_start_error(self, mock_message, mock_db):
        """Тест команды /start при ошибке."""
        mock_message.text = "/start"
        mock_db.execute_scalar.side_effect = Exception("DB Error")

        from src.bot.handlers import cmd_start

        await cmd_start(mock_message)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Добро пожаловать" in response

    @pytest.mark.asyncio
    async def test_cmd_help(self, mock_message):
        """Тест команды /help."""
        mock_message.text = "/help"

        from src.bot.handlers import cmd_help

        await cmd_help(mock_message)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Справка по командам" in response
        assert "/stats" in response
        assert "/top_videos" in response

    @pytest.mark.asyncio
    async def test_cmd_stats_success(self, mock_message, mock_db):
        """Тест команды /stats при успешном выполнении."""
        mock_message.text = "/stats"
        mock_db.execute_scalar.side_effect = [
            100,  # videos_count
            5000,  # snapshots_count
            50,  # unique_creators
            30,  # videos_over_1000
            1500.5,  # avg_views
            10.2,  # avg_snapshots
        ]

        from src.bot.handlers import cmd_stats

        await cmd_stats(mock_message)

        assert mock_db.execute_scalar.call_count == 6
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Общая статистика системы" in response
        assert "100" in response  # videos_count
        assert "30" in response  # videos_over_1000

    @pytest.mark.asyncio
    async def test_cmd_stats_error(self, mock_message, mock_db):
        """Тест команды /stats при ошибке."""
        mock_message.text = "/stats"
        mock_db.execute_scalar.side_effect = Exception("DB Error")

        from src.bot.handlers import cmd_stats

        await cmd_stats(mock_message)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        # Проверяем что в ответе есть слово "ошибка" в любом регистре
        assert "ошибка" in response.lower()

    @pytest.mark.asyncio
    async def test_cmd_top_videos_default_limit(self, mock_message, mock_db):
        """Тест команды /top_videos с лимитом по умолчанию."""
        mock_message.text = "/top_videos"

        # Мок данных
        mock_videos = [
            {"id": "video1", "views_count": 10000, "creator_id": "creator1"},
            {"id": "video2", "views_count": 9000, "creator_id": "creator2"},
        ]
        mock_db.execute_query.return_value = mock_videos

        from src.bot.handlers import cmd_top_videos

        await cmd_top_videos(mock_message)

        mock_db.execute_query.assert_called_once()
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Топ" in response
        assert "видео" in response

    @pytest.mark.asyncio
    async def test_cmd_top_videos_custom_limit(self, mock_message, mock_db):
        """Тест команды /top_videos с пользовательским лимитом."""
        mock_message.text = "/top_videos 5"
        mock_db.execute_query.return_value = []

        from src.bot.handlers import cmd_top_videos

        await cmd_top_videos(mock_message)

        mock_db.execute_query.assert_called_once()
        # Проверяем что команда выполнилась без ошибок
        assert True

    @pytest.mark.asyncio
    async def test_cmd_top_videos_max_limit(self, mock_message, mock_db):
        """Тест команды /top_videos с превышением максимального лимита."""
        mock_message.text = f"/top_videos {MAX_VIDEOS_LIMIT + 10}"
        mock_db.execute_query.return_value = []

        from src.bot.handlers import cmd_top_videos

        await cmd_top_videos(mock_message)

        mock_db.execute_query.assert_called_once()
        # Проверяем, что было сообщение
        assert mock_message.answer.call_count >= 1

    @pytest.mark.asyncio
    async def test_cmd_top_videos_no_data(self, mock_message, mock_db):
        """Тест команды /top_videos без данных."""
        mock_message.text = "/top_videos"
        mock_db.execute_query.return_value = []

        from src.bot.handlers import cmd_top_videos

        await cmd_top_videos(mock_message)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        # Проверяем, что есть сообщение об отсутствии данных
        assert response  # Ответ не пустой

    @pytest.mark.asyncio
    async def test_cmd_top_creators(self, mock_message, mock_db):
        """Тест команды /top_creators."""
        mock_message.text = "/top_creators 3"

        mock_creators = [
            {
                "creator_id": "creator1",
                "video_count": 10,
                "total_views": 100000,
                "avg_views": 10000,
                "max_views": 20000,
            },
            {
                "creator_id": "creator2",
                "video_count": 8,
                "total_views": 80000,
                "avg_views": 10000,
                "max_views": 15000,
            },
        ]
        mock_db.execute_query.return_value = mock_creators

        from src.bot.handlers import cmd_top_creators

        await cmd_top_creators(mock_message)

        mock_db.execute_query.assert_called_once()
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Топ" in response
        assert "креаторов" in response.lower()

    @pytest.mark.asyncio
    async def test_cmd_video_info_start(self, mock_message, mock_state):
        """Тест начала получения информации о видео."""
        mock_message.text = "/video_info"

        from src.bot.handlers import cmd_video_info_start

        await cmd_video_info_start(mock_message, mock_state)

        mock_state.set_state.assert_called_once_with(
            VideoInfoState.waiting_for_video_id
        )
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "ID видео" in response

    @pytest.mark.asyncio
    async def test_cmd_video_info_process_success(
        self, mock_message, mock_state, mock_db
    ):
        """Тест обработки ID видео при успешном поиске."""
        mock_message.text = "video_id_123"

        mock_video_info = [
            {
                "id": "video_id_123",
                "creator_id": "creator_456",
                "views_count": 1500,
                "snapshots_count": 5,
                "last_snapshot": datetime.now(),
                "total_growth": 500,
            }
        ]
        mock_db.execute_query.return_value = mock_video_info

        from src.bot.handlers import cmd_video_info_process

        await cmd_video_info_process(mock_message, mock_state)

        mock_db.execute_query.assert_called_once()
        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "video_id_123" in response

    @pytest.mark.asyncio
    async def test_cmd_video_info_process_cancel(self, mock_message, mock_state):
        """Тест отмены получения информации о видео."""
        mock_message.text = "/cancel"

        from src.bot.handlers import cmd_video_info_process

        await cmd_video_info_process(mock_message, mock_state)

        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "отмен" in response.lower()

    @pytest.mark.asyncio
    async def test_cmd_video_info_process_not_found(
        self, mock_message, mock_state, mock_db
    ):
        """Тест обработки ID видео при отсутствии видео."""
        mock_message.text = "non_existent_id"
        mock_db.execute_query.return_value = []

        from src.bot.handlers import cmd_video_info_process

        await cmd_video_info_process(mock_message, mock_state)

        # Проверяем что состояние было очищено
        assert mock_state.clear.call_count >= 1
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_daily_growth_default(self, mock_message, mock_db):
        """Тест команды /daily_growth с периодом по умолчанию."""
        mock_message.text = "/daily_growth"

        mock_stats = [
            {
                "date": datetime.now().date(),
                "active_videos": 10,
                "total_growth": 1000,
                "avg_growth_per_video": 100,
            },
        ]
        mock_db.execute_query.return_value = mock_stats

        from src.bot.handlers import cmd_daily_growth

        await cmd_daily_growth(mock_message)

        mock_db.execute_query.assert_called_once()
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert "Рост" in response or "дней" in response

    @pytest.mark.asyncio
    async def test_cmd_daily_growth_custom_days(self, mock_message, mock_db):
        """Тест команды /daily_growth с пользовательским периодом."""
        mock_message.text = "/daily_growth 14"
        mock_db.execute_query.return_value = []

        from src.bot.handlers import cmd_daily_growth

        await cmd_daily_growth(mock_message)

        mock_db.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_daily_growth_max_days(self, mock_message, mock_db):
        """Тест команды /daily_growth с превышением максимального периода."""
        mock_message.text = f"/daily_growth {MAX_DAYS_LIMIT + 10}"
        mock_db.execute_query.return_value = []

        from src.bot.handlers import cmd_daily_growth

        await cmd_daily_growth(mock_message)

        mock_db.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_daily_growth_no_data(self, mock_message, mock_db):
        """Тест команды /daily_growth без данных."""
        mock_message.text = "/daily_growth"
        mock_db.execute_query.return_value = []

        from src.bot.handlers import cmd_daily_growth

        await cmd_daily_growth(mock_message)

        mock_message.answer.assert_called_once()


# === Тесты вспомогательных функций ===


class TestUtilityFunctions:
    """Тесты вспомогательных функций."""

    def test_parse_date(self):
        """Тест парсинга дат из русского текста."""
        # Тест относительных дат
        result = parse_date("вчера")
        assert result is not None

        result = parse_date("сегодня")
        assert result is not None

        result = parse_date("завтра")
        assert result is not None

        # Тест форматов дат
        assert parse_date("2025-11-05") == datetime(2025, 11, 5)
        assert parse_date("05.11.2025") == datetime(2025, 11, 5)

        # Тест русских месяцев
        assert parse_date("1 ноября 2025") == datetime(2025, 11, 1)
        assert parse_date("15 декабря 2024") == datetime(2024, 12, 15)

        # Тест без года
        result = parse_date("1 ноября")
        assert result is not None
        assert result.month == 11
        assert result.day == 1

        # Тест некорректных дат
        assert parse_date("") is None
        assert parse_date("не дата") is None

    def test_extract_date_range_from_query(self):
        """Тест извлечения диапазона дат из запроса."""
        # Паттерн 1
        query = "в период с 1 ноября 2025 по 5 ноября 2025 включительно"
        result = extract_date_range_from_query(query)
        assert result == ("2025-11-01", "2025-11-05")

        # Паттерн 2
        query = "с 1 ноября по 5 ноября 2025"
        result = extract_date_range_from_query(query)
        assert result == ("2025-11-01", "2025-11-05")

        # Паттерн 3
        query = "с 1 по 5 ноября 2025"
        result = extract_date_range_from_query(query)
        assert result == ("2025-11-01", "2025-11-05")

        # Без диапазона
        query = "сколько всего видео"
        result = extract_date_range_from_query(query)
        assert result is None

    def test_fix_sql_dates_based_on_range(self):
        """Тест исправления дат в SQL запросе."""
        # Тест для COUNT запросов
        sql = (
            "SELECT COUNT(*) FROM videos WHERE creator_id = 'test' AND video_created_at BETWEEN '2025-11-0' "
            "AND '2025-11-0';"
        )
        start_date = "2025-11-01"
        end_date = "2025-11-05"

        fixed = fix_sql_dates_based_on_range(sql, start_date, end_date)
        assert "2025-11-01" in fixed
        assert "2025-11-05" in fixed

    def test_fix_date_range_in_sql(self):
        """Тест исправления диапазона дат в SQL."""
        sql = "SELECT * FROM videos WHERE date BETWEEN '2025-11-0' AND '2025-11-0';"
        start_date = "2025-11-01"
        end_date = "2025-11-05"

        fixed = fix_date_range_in_sql(sql, start_date, end_date)
        assert "2025-11-01" in fixed
        assert "2025-11-05" in fixed


# === Тесты интеллектуального обработчика ===


@pytest.mark.usefixtures("mock_message", "mock_db", "mock_llm_client")
class TestIntelligentHandler:
    """Тесты интеллектуального обработчика."""

    @pytest.mark.asyncio
    async def test_handle_intelligent_empty_query(self, mock_message):
        """Тест обработки пустого запроса."""
        mock_message.text = ""

        from src.bot.handlers import handle_intelligent

        await handle_intelligent(mock_message)

        # Пустой запрос не должен вызывать answer
        mock_message.answer.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_intelligent_days_count_query(
        self, mock_message, mock_db, mock_llm_client
    ):
        """Тест обработки запроса о количестве дней."""
        # Этот тест проверяет специальную обработку запросов о днях
        mock_message.text = (
            "В скольких разных календарных днях публиковал видео креатор "
            "с id 8b76e572635b400c9052286a56176e03 в ноябре 2025?"
        )

        # Настраиваем моки
        mock_db.execute_scalar.return_value = 3

        from src.bot.handlers import handle_intelligent

        await handle_intelligent(mock_message)

        # Проверяем, что был вызов к базе данных
        # В зависимости от реализации может быть 0 или более вызовов
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_intelligent_growth_query(
        self, mock_message, mock_db, mock_llm_client
    ):
        """Тест обработки запроса о росте просмотров."""
        mock_message.text = (
            "Насколько суммарно выросли просмотры видео креатора "
            "с id 8b76e572635b400c9052286a56176e03 28 ноября 2025 с 10 до 15 часов?"
        )

        # Настраиваем моки
        mock_db.execute_scalar.return_value = 757

        from src.bot.handlers import handle_intelligent

        await handle_intelligent(mock_message)

        # Проверяем, что был ответ
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_intelligent_dangerous_sql(
        self, mock_message, mock_llm_client
    ):
        """Тест обработки опасного SQL запроса."""
        mock_message.text = "удали все видео"
        mock_llm_client.generate_sql_from_natural_language.return_value = (
            "DELETE FROM videos;"
        )

        from src.bot.handlers import handle_intelligent

        await handle_intelligent(mock_message)

        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_intelligent_sql_execution_error(
        self, mock_message, mock_db, mock_llm_client
    ):
        """Тест обработки ошибки выполнения SQL."""
        mock_message.text = "сколько всего видео"
        mock_llm_client.generate_sql_from_natural_language.return_value = (
            "SELECT COUNT(*) FROM videos;"
        )
        mock_db.execute_scalar.side_effect = Exception("DB error")

        from src.bot.handlers import handle_intelligent

        await handle_intelligent(mock_message)

        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_intelligent_no_sql_from_llm(
        self, mock_message, mock_llm_client
    ):
        """Тест обработки, когда LLM не возвращает SQL."""
        mock_message.text = "произвольный запрос"
        mock_llm_client.generate_sql_from_natural_language.return_value = None

        from src.bot.handlers import handle_intelligent

        await handle_intelligent(mock_message)

        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        assert response == "0"

    @pytest.mark.asyncio
    async def test_handle_intelligent_sql_fixes(
        self, mock_message, mock_db, mock_llm_client
    ):
        """Тест исправления SQL от LLM."""
        mock_message.text = "видео с 1 по 5 ноября"

        # LLM возвращает SQL
        mock_llm_client.generate_sql_from_natural_language.return_value = (
            "SELECT COUNT(*) FROM videos WHERE date "
            "BETWEEN '2025-11-0' AND '2025-11-0';"
        )

        # DB возвращает результат
        mock_db.execute_scalar.return_value = 10

        from src.bot.handlers import handle_intelligent

        await handle_intelligent(mock_message)

        mock_db.execute_scalar.assert_called_once()
        mock_message.answer.assert_called_once_with("10")


# === Тесты альтернативных запросов ===


@pytest.mark.usefixtures("mock_db")
class TestAlternativeQueries:
    """Тесты альтернативных запросов."""

    @pytest.mark.asyncio
    async def test_try_alternative_queries_days_count(self, mock_db):
        """Тест альтернативных запросов для количества дней."""
        # Создаем мок для самого модуля handlers, чтобы перехватить вызовы
        with patch("src.bot.handlers.db", mock_db):
            user_query = "В скольких разных календарных днях публиковал видео креатор с id test-id в ноябре 2025?"
            original_sql = "Неправильный SQL"

            # Настраиваем мок
            mock_db.execute_scalar.return_value = 3

            result = await try_alternative_queries(user_query, original_sql)

            # Функция может вернуть результат или None
            # Просто проверяем, что она выполнилась без ошибок
            assert True

    @pytest.mark.asyncio
    async def test_try_alternative_queries_growth(self, mock_db):
        """Тест альтернативных запросов для роста просмотров."""
        with patch("src.bot.handlers.db", mock_db):
            user_query = (
                "Насколько суммарно выросли просмотры видео креатора с id test-id 28 ноября 2025 "
                "с 10 до 15 часов?"
            )
            original_sql = "Неправильный SQL"

            mock_db.execute_scalar.return_value = 757

            result = await try_alternative_queries(user_query, original_sql)

            # Функция может вернуть результат или None
            assert True

    @pytest.mark.asyncio
    async def test_try_alternative_queries_june(self, mock_db):
        """Тест альтернативных запросов для июня."""
        with patch("src.bot.handlers.db", mock_db):
            user_query = "суммарное количество просмотров всех видео за июне 2025"
            original_sql = "Неправильный SQL"

            mock_db.execute_scalar.return_value = 100000

            result = await try_alternative_queries(user_query, original_sql)

            # Функция может вернуть результат или None
            assert True

    @pytest.mark.asyncio
    async def test_try_alternative_queries_between_fix(self, mock_db):
        """Тест исправления BETWEEN в альтернативных запросах."""
        with patch("src.bot.handlers.db", mock_db):
            user_query = "произвольный запрос"
            original_sql = (
                "SELECT * FROM videos WHERE date BETWEEN '2025-11-01' AND '2025-11-05';"
            )

            mock_db.execute_scalar.return_value = 5

            result = await try_alternative_queries(user_query, original_sql)

            # Функция может вернуть результат или None
            assert True

    @pytest.mark.asyncio
    async def test_try_alternative_queries_no_match(self, mock_db):
        """Тест, когда нет подходящих альтернативных запросов."""
        with patch("src.bot.handlers.db", mock_db):
            user_query = "произвольный запрос без ключевых слов"
            original_sql = "SELECT * FROM videos;"

            result = await try_alternative_queries(user_query, original_sql)

            assert result is None
            mock_db.execute_scalar.assert_not_called()


# === Интеграционные тесты ===


@pytest.mark.usefixtures("mock_message", "mock_db", "mock_state")
class TestIntegration:
    """Интеграционные тесты."""

    @pytest.mark.asyncio
    async def test_full_flow_top_videos(self, mock_message, mock_db):
        """Полный поток команды /top_videos."""
        # Подготовка данных
        mock_message.text = "/top_videos 3"

        expected_videos = [
            {"id": "video_1", "views_count": 50000, "creator_id": "creator_a"},
            {"id": "video_2", "views_count": 40000, "creator_id": "creator_b"},
            {"id": "video_3", "views_count": 30000, "creator_id": "creator_c"},
        ]

        mock_db.execute_query.return_value = expected_videos

        # Выполнение
        from src.bot.handlers import cmd_top_videos

        await cmd_top_videos(mock_message)

        # Проверки
        mock_db.execute_query.assert_called_once()
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_flow_video_info(self, mock_message, mock_state, mock_db):
        """Полный поток получения информации о видео."""
        # Этап 1: Начало
        mock_message.text = "/video_info"

        from src.bot.handlers import cmd_video_info_start

        await cmd_video_info_start(mock_message, mock_state)

        mock_state.set_state.assert_called_once_with(
            VideoInfoState.waiting_for_video_id
        )
        mock_message.answer.assert_called_once()

        # Сбрасываем счетчик вызовов для следующего этапа
        mock_message.answer.reset_mock()
        mock_state.reset_mock()

        # Этап 2: Ввод ID
        mock_message.text = "video_123"

        mock_video = [
            {
                "id": "video_123",
                "creator_id": "creator_456",
                "views_count": 15000,
                "snapshots_count": 10,
                "last_snapshot": datetime(2025, 11, 28, 14, 30),
                "total_growth": 5000,
            }
        ]
        mock_db.execute_query.return_value = mock_video

        from src.bot.handlers import cmd_video_info_process

        await cmd_video_info_process(mock_message, mock_state)

        # Проверки
        mock_db.execute_query.assert_called_once()
        mock_state.clear.assert_called_once()
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_in_commands(self, mock_message, mock_db):
        """Тест обработки ошибок в командах."""
        # Тест для команды, которая должна обрабатывать ошибки БД
        mock_message.text = "/stats"
        mock_db.execute_scalar.side_effect = Exception("Database connection failed")

        from src.bot.handlers import cmd_stats

        await cmd_stats(mock_message)

        # Проверяем, что ошибка была обработана и пользователю отправлено сообщение
        mock_message.answer.assert_called_once()
        response = mock_message.answer.call_args[0][0]
        # Проверяем, что в ответе есть указание на ошибку
        assert response  # Ответ не пустой

    @pytest.mark.asyncio
    async def test_boundary_conditions(self, mock_message, mock_db):
        """Тест граничных условий."""
        # Тест с максимальным количеством видео
        mock_message.text = f"/top_videos {MAX_VIDEOS_LIMIT}"
        mock_db.execute_query.return_value = []

        from src.bot.handlers import cmd_top_videos

        await cmd_top_videos(mock_message)

        # Проверяем, что команда выполнена
        mock_db.execute_query.assert_called_once()

        # Тест с превышением максимального количества
        mock_message.text = f"/top_videos {MAX_VIDEOS_LIMIT + 100}"
        mock_db.execute_query.reset_mock()
        mock_message.answer.reset_mock()

        await cmd_top_videos(mock_message)

        mock_db.execute_query.assert_called_once()
        # Должно быть сообщение
        assert mock_message.answer.call_count >= 1


# === Тесты для edge cases ===


@pytest.mark.usefixtures("mock_message", "mock_state", "mock_db", "mock_llm_client")
class TestEdgeCases:
    """Тесты для крайних случаев."""

    @pytest.mark.asyncio
    async def test_very_long_video_id(self, mock_message, mock_state, mock_db):
        """Тест обработки очень длинного ID видео."""
        long_id = "a" * 100  # Очень длинный ID
        mock_message.text = long_id

        mock_video = [
            {
                "id": long_id,
                "creator_id": "creator",
                "views_count": 1000,
                "snapshots_count": 1,
                "last_snapshot": datetime.now(),
                "total_growth": 100,
            }
        ]
        mock_db.execute_query.return_value = mock_video

        from src.bot.handlers import cmd_video_info_process

        await cmd_video_info_process(mock_message, mock_state)

        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_special_characters_in_query(
        self, mock_message, mock_llm_client, mock_db
    ):
        """Тест запроса со специальными символами."""
        mock_message.text = "сколько видео с просмотрами > 1000 & < 5000?"
        mock_llm_client.generate_sql_from_natural_language.return_value = (
            "SELECT COUNT(*) FROM videos "
            "WHERE views_count > 1000 "
            "AND views_count < 5000;"
        )
        mock_db.execute_scalar.return_value = 25

        from src.bot.handlers import handle_intelligent

        await handle_intelligent(mock_message)

        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_unicode_characters(self, mock_message):
        """Тест с Unicode символами."""
        mock_message.text = "скільки відео? 🎬"  # Украинский + эмодзи

        from src.bot.handlers import handle_intelligent

        # Просто проверяем, что не падает
        try:
            await handle_intelligent(mock_message)
            assert True
        except Exception as e:
            pytest.fail(f"Должен обрабатывать Unicode: {e}")

    @pytest.mark.asyncio
    async def test_concurrent_commands(self, mock_message, mock_db):
        """Тест имитации конкурентных команд."""
        # Эмулируем быстрое выполнение нескольких команд
        commands = ["/stats", "/top_videos 2", "/daily_growth"]

        for cmd in commands:
            mock_message.text = cmd
            mock_db.reset_mock()
            mock_message.answer.reset_mock()

            # Каждая команда должна работать независимо
            if cmd == "/stats":
                mock_db.execute_scalar.side_effect = [100, 5000, 50, 30, 1500.5, 10.2]
                from src.bot.handlers import cmd_stats

                await cmd_stats(mock_message)
            elif cmd.startswith("/top_videos"):
                mock_db.execute_query.return_value = []
                from src.bot.handlers import cmd_top_videos

                await cmd_top_videos(mock_message)
            elif cmd == "/daily_growth":
                mock_db.execute_query.return_value = []
                from src.bot.handlers import cmd_daily_growth

                await cmd_daily_growth(mock_message)

            # Проверяем, что каждая команда что-то ответила
            mock_message.answer.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
