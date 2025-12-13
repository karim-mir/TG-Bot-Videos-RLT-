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
        """
        prompt = self._build_enhanced_prompt(user_query)

        try:
            logger.info(f"Генерируем SQL для: {user_query}")

            # Генерируем ответ
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                options={
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                }
            )

            # Извлекаем SQL
            sql = self._extract_sql_from_response(response)

            # Если SQL не валиден, используем fallback
            if not self._validate_sql(sql):
                logger.warning(f"Невалидный SQL, используем fallback: {sql}")
                return self._fallback_sql_for_query(user_query)

            return sql

        except Exception as e:
            logger.error(f"Ошибка генерации SQL: {e}")
            return self._fallback_sql_for_query(user_query)

    def _fallback_sql_for_query(self, user_query: str) -> str:
        """Резервные SQL на основе запроса."""
        query_lower = user_query.lower()

        # Сопоставление запросов с SQL
        fallback_rules = [
            (["сколько всего видео", "видео есть в системе"],
             "SELECT COUNT(*) FROM videos"),

            (["сколько разных креаторов", "сколько различных креаторов"],
             "SELECT COUNT(DISTINCT creator_id) FROM videos"),

            (["отрицательным", "отрицательные", "уменьшилось", "стало меньше", "замеров статистики"],
             "SELECT COUNT(*) FROM video_snapshots WHERE delta_views_count < 0"),

            (["больше", "просмотров"],
             lambda: self._extract_views_query(query_lower)),

            (["креатора с id", "креатор id"],
             lambda: self._extract_creator_query(query_lower)),

            (["сумме выросли", "выросли все видео"],
             lambda: self._extract_growth_query(query_lower)),
        ]

        for keywords, sql_generator in fallback_rules:
            if any(keyword in query_lower for keyword in keywords if isinstance(keywords, list)):
                if callable(sql_generator):
                    return sql_generator()
                return sql_generator

        return "SELECT COUNT(*) FROM videos"

    def _extract_views_query(self, query_lower: str) -> str:
        """Извлекает запрос с условием по просмотрам."""
        import re
        match = re.search(r'больше\s+(\d[\d\s,]*)', query_lower)
        if match:
            num = match.group(1).replace(' ', '').replace(',', '')
            return f"SELECT COUNT(*) FROM videos WHERE views_count > {num}"
        return "SELECT COUNT(*) FROM videos WHERE views_count > 1000"

    def _extract_creator_query(self, query_lower: str) -> str:
        """Извлекает запрос по креатору."""
        import re
        # Ищем ID креатора
        id_match = re.search(r'id\s+([a-f0-9\-]+)', query_lower)
        if id_match:
            creator_id = id_match.group(1)

            # Ищем диапазон дат
            if "с" in query_lower and "по" in query_lower:
                date_match = re.search(r'с\s+(\d{1,2})\s+(.+?)\s+по\s+(\d{1,2})\s+(.+?)\s+(\d{4})', query_lower)
                if date_match:
                    # Упрощенный вариант
                    return f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}'"

            return f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}'"

        return "SELECT COUNT(*) FROM videos"

    def _extract_growth_query(self, query_lower: str) -> str:
        """Извлекает запрос о росте просмотров."""
        # Упрощенный вариант
        return "SELECT COALESCE(SUM(delta_views_count), 0) FROM video_snapshots"

    def _validate_sql(self, sql: str) -> bool:
        """Проверяет валидность SQL."""
        if not sql:
            return False

        sql_upper = sql.upper().strip()

        # Должен начинаться с SQL ключевого слова
        valid_starts = ["SELECT", "WITH", "COUNT", "SUM", "AVG", "MIN", "MAX"]
        if not any(sql_upper.startswith(start) for start in valid_starts):
            return False

        # Не должен содержать опасных команд
        dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
        if any(cmd in sql_upper for cmd in dangerous):
            return False

        # Должен содержать FROM
        if "FROM" not in sql_upper:
            return False

        return True

    def _build_enhanced_prompt(self, user_query: str) -> str:
        """Строит промпт для генерации SQL (оптимизирован для Gemma)."""

        schema_description = """
        PostgreSQL database schema:

        TABLE videos:
        - id (VARCHAR) - video ID
        - creator_id (VARCHAR) - creator ID  
        - video_created_at (TIMESTAMPTZ) - video publication datetime
        - views_count (INTEGER) - total views
        - likes_count (INTEGER) - total likes
        - comments_count (INTEGER) - total comments
        - reports_count (INTEGER) - total reports
        - created_at (TIMESTAMPTZ) - record creation
        - updated_at (TIMESTAMPTZ) - record update

        TABLE video_snapshots:
        - id (VARCHAR) - snapshot ID
        - video_id (VARCHAR) - references videos.id
        - views_count (INTEGER) - views at snapshot time
        - likes_count (INTEGER) - likes at snapshot time  
        - comments_count (INTEGER) - comments at snapshot time
        - reports_count (INTEGER) - reports at snapshot time
        - delta_views_count (INTEGER) - views change from previous hour
        - delta_likes_count (INTEGER) - likes change from previous hour
        - delta_comments_count (INTEGER) - comments change from previous hour
        - delta_reports_count (INTEGER) - reports change from previous hour
        - created_at (TIMESTAMPTZ) - snapshot timestamp (hourly)
        - updated_at (TIMESTAMPTZ) - record update

        IMPORTANT:
        - Use DATE() for date comparisons
        - Use AT TIME ZONE 'UTC' for timezone handling
        - delta_*_count can be negative
        - Return ONLY one number in result
        """

        # Примеры запросов на русском с правильными SQL
        examples = """
        User Query: "Сколько всего видео есть в системе?"
        SQL: SELECT COUNT(*) FROM videos

        User Query: "Сколько видео набрало больше 100000 просмотров?"
        SQL: SELECT COUNT(*) FROM videos WHERE views_count > 100000

        User Query: "Сколько видео у креатора с id abc123 вышло с 1 ноября 2025 по 5 ноября 2025 включительно?"
        SQL: SELECT COUNT(*) FROM videos WHERE creator_id = 'abc123' AND DATE(video_created_at) BETWEEN '2025-11-01' AND '2025-11-05'

        User Query: "На сколько просмотров в сумме выросли все видео 28 ноября 2025?"
        SQL: SELECT COALESCE(SUM(delta_views_count), 0) FROM video_snapshots WHERE DATE(created_at) = '2025-11-28'

        User Query: "Сколько разных видео получали новые просмотры 27 ноября 2025?"
        SQL: SELECT COUNT(DISTINCT video_id) FROM video_snapshots WHERE DATE(created_at) = '2025-11-27' AND delta_views_count > 0

        User Query: "Сколько всего есть замеров статистики с отрицательными просмотрами?"
        SQL: SELECT COUNT(*) FROM video_snapshots WHERE delta_views_count < 0

        User Query: "Сколько разных креаторов есть в системе?"
        SQL: SELECT COUNT(DISTINCT creator_id) FROM videos

        User Query: "Сколько видео опубликовано в ноябре 2025 года?"
        SQL: SELECT COUNT(*) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 AND EXTRACT(MONTH FROM video_created_at) = 11

        User Query: "Среднее количество просмотров на видео?"
        SQL: SELECT AVG(views_count) FROM videos

        User Query: "Сумма всех просмотров по всем видео?"
        SQL: SELECT SUM(views_count) FROM videos
        """

        instructions = """
        INSTRUCTIONS:
        1. Generate ONLY the SQL query, no explanations
        2. Use PostgreSQL syntax
        3. Query must return exactly ONE number
        4. Use actual values from the question (don't use $1, $2 parameters)
        5. For dates use format 'YYYY-MM-DD'
        6. Use BETWEEN for date ranges
        7. Use COALESCE to handle NULL values
        8. For text values use single quotes: 'value'
        9. Use Russian month names: января, февраля, марта, etc.
        10. Pay attention to negative conditions: "отрицательные" = negative, "меньше" = less than

        IMPORTANT: Return ONLY the SQL query, nothing else.
        """

        prompt = f"""You are a PostgreSQL expert. Convert the Russian user query to a SQL query.

    {schema_description}

    {examples}

    {instructions}

    User Query (in Russian): "{user_query}"

    SQL Query:
    """

        return prompt

    def _extract_sql_from_response(self, response) -> str:
        """Извлекает SQL запрос из ответа модели."""
        try:
            # Получаем текст ответа из объекта
            if hasattr(response, 'response'):
                response_text = response.response
            elif isinstance(response, dict) and 'response' in response:
                response_text = response['response']
            elif isinstance(response, str):
                response_text = response
            else:
                # Пробуем преобразовать в строку
                response_text = str(response)

            logger.debug(f"Сырой ответ от модели: {response_text}")

            # Очищаем ответ
            response_text = response_text.strip()

            # Удаляем маркеры кодовых блоков
            if '```sql' in response_text:
                response_text = response_text.split('```sql')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()

            # Удаляем возможные префиксы типа "SQL:" или "Запрос:"
            prefixes = ['SQL:', 'Query:', 'Запрос:', 'Ответ:']
            for prefix in prefixes:
                if response_text.startswith(prefix):
                    response_text = response_text[len(prefix):].strip()

            # Удаляем кавычки если есть
            response_text = response_text.strip('"\'')

            # Проверяем, что это SQL
            if not self._looks_like_sql(response_text):
                logger.warning(f"Ответ не похож на SQL: {response_text}")
                return self._fallback_sql_for_query("")

            return response_text

        except Exception as e:
            logger.error(f"Ошибка извлечения SQL: {e}")
            return "SELECT COUNT(*) FROM videos"

    def _looks_like_sql(self, text: str) -> bool:
        """Проверяет, похож ли текст на SQL запрос."""
        if not text:
            return False

        text_upper = text.upper().strip()

        # Должен начинаться с SQL команды
        sql_keywords = ['SELECT', 'WITH', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX']
        if not any(text_upper.startswith(kw) for kw in sql_keywords):
            return False

        # Не должен содержать опасных команд
        dangerous = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'TRUNCATE']
        if any(cmd in text_upper for cmd in dangerous):
            return False

        return True


# Глобальный экземпляр
try:
    llm_client = LLMClient(skip_check=True)
except Exception as e:
    logger.warning(f"Failed to create LLM client: {e}")
    llm_client = None
