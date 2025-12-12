import logging

import ollama

from src.config import LLM_CONFIG

logger = logging.getLogger(__name__)


class LLMClient:
    """Клиент для работы с локальной LLM через Ollama."""

    def __init__(self, skip_check: bool = False):
        """
        Args:
            skip_check: Если True, пропустить проверку модели при инициализации
        """
        self.model = LLM_CONFIG["model"]
        self.base_url = LLM_CONFIG["base_url"]
        self.max_tokens = LLM_CONFIG["max_tokens"]
        self.temperature = LLM_CONFIG["temperature"]

        ollama_host = self.base_url.replace("http://", "").replace("https://", "")
        self.client = ollama.Client(host=ollama_host)

        if not skip_check:
            try:
                self._check_model()
            except Exception as e:
                logger.error(f"Failed to check model: {e}")

    def _check_model(self):
        """Проверяет, доступна ли модель"""
        try:
            models = self.client.list()
            available_models = [m["name"] for m in models["models"]]

            if self.model not in available_models:
                logger.warning(
                    f"Model {self.model} not found. Available: {available_models}"
                )
                logger.info(f"Trying to pull model {self.model}...")
                self.client.pull(self.model)
                logger.info(f"Model {self.model} pulled successfully")
        except Exception as e:
            logger.error(f"Failed to check model: {e}")
            raise

    def generate_sql_from_natural_language(self, user_query: str) -> str:
        """
        Преобразовывает естественный язык в SQL запрос.
        Args:
            user_query: Запрос пользователя на естественном языке (русский)
        Returns:
            SQL запрос для выполнения
        """
        prompt = self.build_sql_generation_prompt(user_query)

        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            )

            if hasattr(response, "response"):
                response_text = response.response
            elif isinstance(response, dict) and "response" in response:
                response_text = response["response"]
            else:
                response_text = str(response)

            sql_query = self._extract_sql_from_response(response_text)
            logger.debug(f"Generated SQL: {sql_query}")
            return sql_query

        except Exception as e:
            logger.error(f"Failed to generate SQL: {e}")
            return "SELECT COUNT(*) FROM videos"

    def build_sql_generation_prompt(self, user_query: str) -> str:
        """Строит промпт для генерации SQL"""

        schema_description = """

        Database schema:

        1. Table: videos
           Columns:
           - id (VARCHAR) - primary key
           - creator_id (VARCHAR) - creator identifier
           - video_created_at (TIMESTAMP) - when video was published
           - views_count (INTEGER) - final views count
           - likes_count (INTEGER) - final likes count
           - comments_count (INTEGER) - final comments count
           - reports_count (INTEGER) - final reports count
           - created_at (TIMESTAMP) - when record was created
           - updated_at (TIMESTAMP) - when record was updated

        2. Table: video_snapshots
           Columns:
           - id (VARCHAR) - primary key
           - video_id (VARCHAR) - foreign key to videos.id
           - views_count (INTEGER) - views at snapshot time
           - likes_count (INTEGER) - likes at snapshot time
           - comments_count (INTEGER) - comments at snapshot time
           - reports_count (INTEGER) - reports at snapshot time
           - delta_views_count (INTEGER) - views change from previous snapshot
           - delta_likes_count (INTEGER) - likes change from previous snapshot
           - delta_comments_count (INTEGER) - comments change from previous snapshot
           - delta_reports_count (INTEGER) - reports change from previous snapshot
           - created_at (TIMESTAMP) - snapshot time (hourly)
           - updated_at (TIMESTAMP) - when record was updated

        Important notes:
        - Dates in queries should use DATE() function for date comparisons
        - Use CAST(... AS DATE) to extract date from timestamp
        - video_snapshots.created_at is hourly snapshots
        - videos.video_created_at is when video was published
        - delta_* columns show change from previous hour
        """

        examples = """
                Examples:

                User: "Сколько всего видео есть в системе?"
                SQL: SELECT COUNT(*) FROM videos

                User: "Сколько видео у креатора с id 123 вышло с 1 ноября 2025 по 5 ноября 2025 включительно?"
                SQL: SELECT COUNT(*) FROM videos WHERE creator_id = '123' AND video_created_at >= '2025-11-01'
                AND video_created_at <= '2025-11-05'

                User: "Сколько видео набрало больше 100000 просмотров за всё время?"
                SQL: SELECT COUNT(*) FROM videos WHERE views_count > 100000

                User: "На сколько просмотров в сумме выросли все видео 28 ноября 2025?"
                SQL: SELECT SUM(delta_views_count) FROM video_snapshots WHERE DATE(created_at) = '2025-11-28'

                User: "Сколько разных видео получали новые просмотры 27 ноября 2025?"
                SQL: SELECT COUNT(DISTINCT video_id) FROM video_snapshots WHERE DATE(created_at) = '2025-11-27'
                AND delta_views_count > 0
                """

        prompt = f"""{schema_description}

                {examples}

                Instructions:
                1. Generate ONLY SQL query, no explanations
                2. Use PostgreSQL syntax
                3. Return only one number (use COUNT, SUM, etc.)
                4. User query is in Russian, but write SQL in English
                5. For date comparisons, use DATE() function

                User query: {user_query}

                SQL: """

        return prompt

    def _extract_sql_from_response(self, response: str) -> str:
        """Извлекает SQL запрос из ответа модели."""
        # Очищаем ответ: удаляем markdown кодовые блоки если есть
        if "```sql" in response:
            response = response.split("```sql")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()

        # Удаляем лишние пробелы и переносы строк
        response = response.strip()

        # Убедимся, что это SQL запрос (начинается с SELECT, COUNT, SUM и т.д.)
        sql_keywords = ["SELECT", "COUNT", "SUM", "AVG", "MIN", "MAX", "WITH"]
        if not any(response.upper().startswith(kw) for kw in sql_keywords):
            logger.warning(f"Response doesn't look like SQL: {response}")
            # Возвращаем простой запрос по умолчанию
            return "SELECT COUNT(*) FROM videos"

        return response


# Глобальный экземпляр
try:
    llm_client = LLMClient(skip_check=True)
except Exception as e:
    logger.warning(f"Failed to create LLM client: {e}")
    llm_client = None
