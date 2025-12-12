import logging
import os
import sys
import unittest
from unittest.mock import Mock

from src.core.llm_client import LLMClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLLMClient(unittest.TestCase):
    """Тесты для LLMClient"""

    def setUp(self):
        """Настройка перед каждым тестом."""
        # Отключаем логирование для тестов
        logging.getLogger("src.core.llm_client").setLevel(logging.CRITICAL)

        # Создаем экземпляр с пропуском проверки модели
        self.llm_client = LLMClient(skip_check=True)
        # Мокаем клиент Ollama
        self.llm_client.client = Mock()

    def test_build_sql_generation_prompt(self):
        """Тест построения промпта."""
        user_query = "Сколько всего видео есть в системе?"
        prompt = self.llm_client.build_sql_generation_prompt(user_query)

        self.assertIn(user_query, prompt)
        self.assertIn("Database schema:", prompt)
        self.assertIn("Examples:", prompt)
        self.assertIn("Instructions:", prompt)

    def test_extract_sql_from_response_clean(self):
        """Тест извлечения SQL из чистого ответа."""
        response = "SELECT COUNT(*) FROM videos"
        sql = self.llm_client._extract_sql_from_response(response)
        self.assertEqual(sql, "SELECT COUNT(*) FROM videos")

    def test_extract_sql_from_response_with_markdown(self):
        """Тест извлечения SQL из ответа с markdown."""
        response = "```sql\nSELECT COUNT(*) FROM videos\n```"
        sql = self.llm_client._extract_sql_from_response(response)
        self.assertEqual(sql, "SELECT COUNT(*) FROM videos")

    def test_extract_sql_from_response_invalid(self):
        """Тест извлечения SQL из невалидного ответа."""
        response = "Это не SQL запрос"
        sql = self.llm_client._extract_sql_from_response(response)
        self.assertEqual(sql, "SELECT COUNT(*) FROM videos")

    def test_generate_sql_success(self):
        """Тест успешной генерации SQL."""
        # Настраиваем mock ответ
        mock_response = Mock()
        mock_response.response = "SELECT COUNT(*) FROM videos"
        self.llm_client.client.generate.return_value = mock_response

        sql = self.llm_client.generate_sql_from_natural_language("Сколько видео?")
        self.assertEqual(sql, "SELECT COUNT(*) FROM videos")
        self.llm_client.client.generate.assert_called_once()

    def test_generate_sql_failure(self):
        """Тест генерации SQL с ошибкой."""
        self.llm_client.client.generate.side_effect = Exception("Ошибка API")
        sql = self.llm_client.generate_sql_from_natural_language("Сколько видео?")
        self.assertEqual(sql, "SELECT COUNT(*) FROM videos")


if __name__ == "__main__":
    logging.basicConfig(level=logging.CRITICAL)
    unittest.main()
