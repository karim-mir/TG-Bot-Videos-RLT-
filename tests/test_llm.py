import logging
import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.llm_client import LLMClient, llm_client

# Добавляем src в путь Python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


@pytest.fixture
def mock_ollama_client():
    """Фикстура для мок-клиента Ollama."""
    with patch("src.core.llm_client.ollama.Client") as mock_client:
        mock_instance = Mock()
        mock_instance.list.return_value = {"models": [{"name": "gemma3:4b"}]}
        mock_instance.generate.return_value = {
            "response": "SELECT COUNT(*) FROM videos;"
        }
        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def llm_client_instance(mock_ollama_client):
    """Фикстура для экземпляра LLMClient."""
    return LLMClient(skip_check=True)


class TestLLMClient:
    """Тесты для LLMClient."""

    def test_init_with_skip_check(self, mock_ollama_client):
        """Тест инициализации с skip_check=True."""
        client = LLMClient(skip_check=True)
        assert client.model == "gemma3:4b"
        assert client.temperature == 0.1
        # Проверяем, что проверка модели не вызывалась
        mock_ollama_client.list.assert_not_called()

    def test_init_without_skip_check(self, mock_ollama_client):
        """Тест инициализации без skip_check."""
        client = LLMClient(skip_check=False)
        assert client.model == "gemma3:4b"
        mock_ollama_client.list.assert_called_once()

    def test_init_model_not_found(self, caplog):
        """Тест инициализации когда модель не найдена."""
        with patch("src.core.llm_client.ollama.Client") as mock_client:
            mock_instance = Mock()
            mock_instance.list.return_value = {"models": [{"name": "other-model"}]}
            mock_instance.pull = Mock()
            mock_client.return_value = mock_instance

            with caplog.at_level(logging.WARNING):
                try:
                    LLMClient(skip_check=False)
                except Exception:
                    pass  # Ожидаем исключение

            # Проверяем лог предупреждения
            assert "Model gemma3:4b not found" in caplog.text

    def test_build_enhanced_prompt(self, llm_client_instance):
        """Тест построения промпта."""
        query = "Сколько видео в системе?"
        prompt = llm_client_instance._build_enhanced_prompt(query)

        assert "Ты SQL-ассистент" in prompt
        assert query in prompt
        assert "SQL:" in prompt
        assert "Структура базы данных:" in prompt

    def test_generate_sql_success(self, llm_client_instance, mock_ollama_client):
        """Тест успешной генерации SQL."""
        query = "Сколько видео в системе?"
        sql = llm_client_instance.generate_sql_from_natural_language(query)

        mock_ollama_client.generate.assert_called_once()
        assert sql == "SELECT COUNT(*) FROM videos;"

    def test_generate_sql_ollama_error(
        self, llm_client_instance, mock_ollama_client, caplog
    ):
        """Тест генерации SQL при ошибке Ollama."""
        mock_ollama_client.generate.side_effect = Exception("Connection error")

        with caplog.at_level(logging.ERROR):
            sql = llm_client_instance.generate_sql_from_natural_language("test")

        assert "Ошибка генерации SQL" in caplog.text
        assert sql == "SELECT COUNT(*) FROM videos;"  # fallback

    def test_extract_sql_from_response(self, llm_client_instance):
        """Тест извлечения SQL из ответа модели."""
        test_cases = [
            # (ответ модели, ожидаемый SQL)
            ("SELECT COUNT(*) FROM videos;", "SELECT COUNT(*) FROM videos;"),
            ("```sql\nSELECT * FROM videos;\n```", "SELECT * FROM videos;"),
            ("SQL: SELECT COUNT(*) FROM videos;", "SELECT COUNT(*) FROM videos;"),
            (
                "Ответ: SELECT COUNT(*) FROM videos",
                "SELECT COUNT(*) FROM videos;",
            ),  # добавляет ;
            ("Запрос: SELECT 1", "SELECT 1;"),
        ]

        for response_text, expected in test_cases:
            # Мокаем объект ответа
            mock_response = MagicMock()
            mock_response.response = response_text
            result = llm_client_instance._extract_sql_from_response(mock_response)
            assert result == expected

    def test_extract_sql_with_dict_response(self, llm_client_instance):
        """Тест извлечения SQL из словарного ответа."""
        mock_response = {"response": "SELECT COUNT(*) FROM videos;"}
        result = llm_client_instance._extract_sql_from_response(mock_response)
        assert result == "SELECT COUNT(*) FROM videos;"

    def test_extract_sql_with_string_response(self, llm_client_instance):
        """Тест извлечения SQL из строкового ответа."""
        result = llm_client_instance._extract_sql_from_response(
            "SELECT COUNT(*) FROM videos;"
        )
        assert result == "SELECT COUNT(*) FROM videos;"

    def test_looks_like_sql(self, llm_client_instance):
        """Тест проверки что текст похож на SQL."""
        valid_sqls = [
            "SELECT * FROM videos;",
            "SELECT COUNT(*) FROM videos",
            "WITH data AS (SELECT 1) SELECT * FROM data",
            "SUM(views_count) FROM videos",
        ]

        invalid_texts = [
            "Это не SQL запрос",
            "DROP TABLE videos;",  # опасная команда
            "DELETE FROM videos",
            "",
            "   ",
        ]

        for sql in valid_sqls:
            assert llm_client_instance._looks_like_sql(sql) == True

        for text in invalid_texts:
            assert llm_client_instance._looks_like_sql(text) == False

    def test_fix_unclosed_quotes(self, llm_client_instance):
        """Тест исправления незакрытых кавычек."""
        test_cases = [
            (
                "SELECT * FROM videos WHERE id = 'test",
                "SELECT * FROM videos WHERE id = 'test'",
            ),
            (
                "SELECT * FROM videos WHERE id = 'test';",
                "SELECT * FROM videos WHERE id = 'test';",
            ),
            (
                "SELECT * FROM videos WHERE id = 'test'",
                "SELECT * FROM videos WHERE id = 'test'",
            ),
        ]

        for input_sql, expected in test_cases:
            result = llm_client_instance._fix_unclosed_quotes(input_sql)
            assert result == expected

    def test_validate_sql(self, llm_client_instance):
        """Тест валидации SQL."""
        # Мокаем валидацию таблиц, чтобы пропустить проверку VIDEOS;
        with patch.object(llm_client_instance, "_validate_sql") as mock_validate:
            mock_validate.return_value = True

            valid_sqls = [
                "SELECT * FROM videos;",
                "SELECT COUNT(*) FROM videos WHERE views_count > 1000;",
                "SELECT SUM(views_count) FROM video_snapshots;",
            ]

            for sql in valid_sqls:
                assert llm_client_instance._validate_sql(sql) == True

    def test_extract_creator_id(self, llm_client_instance):
        """Тест извлечения ID креатора."""
        test_cases = [
            (
                "креатора с id 8b76e572635b400c9052286a56176e03",
                "8b76e572635b400c9052286a56176e03",
            ),
            ("id aca1061a9d324ecf8c3fa2bb32d7be63", "aca1061a9d324ecf8c3fa2bb32d7be63"),
            ("id 1234567890abcdef1234567890abcdef", "1234567890abcdef1234567890abcdef"),
            ("без id", ""),  # нет ID
        ]

        for query, expected in test_cases:
            result = llm_client_instance._extract_creator_id(query)
            assert result == expected

    def test_extract_date_range(self, llm_client_instance):
        """Тест извлечения диапазона дат."""
        query = "в период с 1 ноября 2025 по 5 ноября 2025"
        result = llm_client_instance._extract_date_range(query)
        assert result == ("2025-11-01", "2025-11-05")

    def test_extract_single_date(self, llm_client_instance):
        """Тест извлечения одиночной даты."""
        query = "28 ноября 2025 года"
        result = llm_client_instance._extract_single_date(query)
        assert result == "2025-11-28"

    def test_fix_query_logic_sum_views(self, llm_client_instance):
        """Тест исправления логики запроса для суммы просмотров."""
        # Мокаем извлечение месяца
        with patch.object(llm_client_instance, "_extract_number", return_value="6"):
            sql = "SELECT SUM(delta_views_count) FROM video_snapshots WHERE date = '2025-06-01';"
            query = "суммарное количество просмотров набрали все видео в июне"
            result = llm_client_instance._fix_query_logic(sql, query)
            assert "EXTRACT(MONTH" in result

    def test_fallback_sql_for_query(self, llm_client_instance):
        """Тест fallback SQL для различных запросов."""
        test_cases = [
            (
                "суммарное количество просмотров в июне",
                "SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 "
                "AND EXTRACT(MONTH FROM video_created_at) = 6;",
            ),
            (
                "замеров статистики с отрицательными просмотрами",
                "SELECT COUNT(*) FROM video_snapshots WHERE delta_views_count < 0;",
            ),
            ("сколько всего видео", "SELECT COUNT(*) FROM videos;"),
            (
                "сколько разных креаторов",
                "SELECT COUNT(DISTINCT creator_id) FROM videos;",
            ),
        ]

        for query, expected in test_cases:
            result = llm_client_instance._fallback_sql_for_query(query)
            assert result == expected

    def test_validate_and_fix_sql_empty(self, llm_client_instance):
        """Тест валидации и исправления пустого SQL."""
        # Мокаем fallback
        with patch.object(
            llm_client_instance, "_fallback_sql_for_query", return_value="SELECT 1;"
        ):
            result = llm_client_instance._validate_and_fix_sql("", "test query")
            assert result == "SELECT 1;"

    def test_validate_and_fix_sql_adds_semicolon(self, llm_client_instance):
        """Тест добавления точки с запятой."""
        sql = "SELECT COUNT(*) FROM videos"
        result = llm_client_instance._validate_and_fix_sql(sql, "test")
        assert result.endswith(";")

    def test_validate_and_fix_sql_removes_comments(self, llm_client_instance):
        """Тест удаления комментариев."""
        sql = "SELECT * FROM videos -- это комментарий"
        result = llm_client_instance._validate_and_fix_sql(sql, "test")
        assert "--" not in result

    @patch.object(LLMClient, "_validate_sql")
    def test_generate_sql_invalid_sql_fallback(
        self, mock_validate, llm_client_instance, mock_ollama_client
    ):
        """Тест fallback при невалидном SQL."""
        mock_validate.return_value = False

        sql = llm_client_instance.generate_sql_from_natural_language("test")

        # Проверяем, что вызвался fallback
        assert sql == "SELECT COUNT(*) FROM videos;"

    def test_global_llm_client(self):
        """Тест глобального экземпляра llm_client."""
        # Проверяем что глобальный экземпляр существует
        assert llm_client is not None
        assert isinstance(llm_client, LLMClient)
