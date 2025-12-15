python
import logging
import re

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
                    "temperature": 0.1,  # СНИЖАЕМ температуру для точности
                    "num_predict": 100,  # Уменьшаем длину ответа
                    "stop": ["\n", ";", "```", "Вопрос:"]  # Стоп-слова
                }
            )

            # Извлекаем SQL
            sql = self._extract_sql_from_response(response)

            # Валидируем и исправляем
            sql = self._validate_and_fix_sql(sql, user_query)

            if not self._validate_sql(sql):
                logger.warning(f"Невалидный SQL, используем fallback: {sql}")
                return self._fallback_sql_for_query(user_query)

            logger.info(f"Сгенерирован SQL: {sql}")
            return sql

        except Exception as e:
            logger.error(f"Ошибка генерации SQL: {e}")
            return self._fallback_sql_for_query(user_query)

    def _build_enhanced_prompt(self, user_query: str) -> str:
        """Строит простой промпт для Gemma3:4b."""

        prompt = f"""
Ты SQL-ассистент. Ответь ТОЛЬКО SQL запросом.

Таблицы:
1. videos (id, creator_id, views_count, likes_count, comments_count, reports_count, video_created_at)
2. video_snapshots (video_id, views_count, likes_count, delta_views_count, delta_likes_count, created_at)

Примеры:
Вопрос: Сколько всего видео?
SQL: SELECT COUNT(*) FROM videos

Вопрос: Сколько видео с просмотрами больше 10000?
SQL: SELECT COUNT(*) FROM videos WHERE views_count > 10000

Вопрос: Сколько видео у креатора abc123?
SQL: SELECT COUNT(*) FROM videos WHERE creator_id = 'abc123'

Вопрос: Сумма просмотров всех видео?
SQL: SELECT SUM(views_count) FROM videos

Вопрос: Дельты просмотров за 2025-11-26?
SQL: SELECT SUM(delta_views_count) FROM video_snapshots WHERE DATE(created_at) = '2025-11-26'

Вопрос: {user_query}
SQL:"""

        return prompt.strip()

    def _validate_and_fix_sql(self, sql: str, user_query: str) -> str:
        """Валидирует и исправляет SQL для Gemma."""
        if not sql:
            return self._fallback_sql_for_query(user_query)

        sql = sql.strip()

        # Если SQL слишком длинный или содержит лишнее
        if '\n' in sql and sql.count('\n') > 3:
            # Берем только первую строку, похожую на SQL
            lines = sql.split('\n')
            for line in lines:
                if line.upper().startswith('SELECT'):
                    sql = line.strip()
                    break

        # Очищаем от комментариев
        if '--' in sql:
            sql = sql.split('--')[0].strip()

        # Добавляем FROM если его нет
        if 'SELECT' in sql.upper() and 'FROM' not in sql.upper():
            # Пробуем исправить простые случаи
            if 'videos' in sql.lower() and 'creator_id' in sql.lower():
                # Пример: SELECT COUNT(*) WHERE creator_id = 'id'
                count_match = re.search(r'SELECT\s+(.+?)\s+WHERE', sql, re.IGNORECASE)
                if count_match:
                    select_part = count_match.group(1)
                    where_part = sql.split('WHERE', 1)[1]
                    sql = f"SELECT {select_part} FROM videos WHERE {where_part}"

        # Исправляем таблицу
        if 'video_snapshots' in sql.lower() and 'creator_id' in sql.lower():
            # В snapshots нет creator_id, нужно через JOIN
            sql = sql.replace('video_snapshots', 'videos')

        return sql

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

        # Проверяем наличие таблиц
        valid_tables = ["VIDEOS", "VIDEO_SNAPSHOTS"]
        from_index = sql_upper.find("FROM")
        if from_index != -1:
            table_part = sql_upper[from_index + 4:].strip().split()[0]
            if table_part not in valid_tables:
                logger.warning(f"Неизвестная таблица: {table_part}")
                return False

        return True

    def _fallback_sql_for_query(self, user_query: str) -> str:
        """Улучшенные fallback правила."""
        query_lower = user_query.lower()

        # Извлекаем ID креатора и число заранее
        creator_id = self._extract_creator_id(query_lower)
        number = self._extract_number(query_lower)

        fallback_rules = [
            # Креаторы
            (["креатора", "создателя", "creator"],
             f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}'" if creator_id else None),

            # Просмотры
            (["больше", "больш", "превысил", "превысило", "набрали"],
             f"SELECT COUNT(*) FROM videos WHERE views_count > {number}"),

            # Лайки
            (["лайк", "лайков", "likes"],
             f"SELECT SUM(likes_count) FROM videos"),

            # Комментарии
            (["комментар", "comments"],
             f"SELECT SUM(comments_count) FROM videos"),

            # Видео всего
            (["сколько всего видео", "видео есть", "всего видео"],
             "SELECT COUNT(*) FROM videos"),

            # Дельты/изменения
            (["дельта", "изменил", "вырос", "увеличил", "рост"],
             "SELECT SUM(delta_views_count) FROM video_snapshots WHERE delta_views_count > 0"),

            # Отрицательные
            (["отрицательн", "уменьшил", "снизил", "упал"],
             "SELECT COUNT(*) FROM video_snapshots WHERE delta_views_count < 0"),

            # Уникальные креаторы
            (["разных креатор", "уникальн", "различн"],
             "SELECT COUNT(DISTINCT creator_id) FROM videos"),
        ]

        for keywords, sql_template in fallback_rules:
            if any(keyword in query_lower for keyword in keywords):
                if sql_template:
                    # Проверяем, что SQL валиден
                    if 'creator_id' in sql_template and "'" in sql_template and "''" not in sql_template:
                        return sql_template
                    elif sql_template.startswith("SELECT"):
                        return sql_template

        # Дефолтный запрос
        return "SELECT COUNT(*) FROM videos"

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
                return ""

            return response_text

        except Exception as e:
            logger.error(f"Ошибка извлечения SQL: {e}")
            return ""

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

    def _extract_creator_id(self, query_lower: str) -> str:
        """Извлекает ID креатора из запроса."""
        # Ищем UUID (с дефисами)
        uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
        uuid_match = re.search(uuid_pattern, query_lower)
        if uuid_match:
            return uuid_match.group(0)

        # Ищем короткий ID (32 символа без дефисов)
        short_id_pattern = r'[a-f0-9]{32}'
        short_id_match = re.search(short_id_pattern, query_lower)
        if short_id_match:
            return short_id_match.group(0)

        # Ищем после "id "
        id_match = re.search(r'id\s+([a-f0-9\-]+)', query_lower)
        if id_match:
            return id_match.group(1)

        return ""

    def _extract_number(self, query_lower: str) -> str:
        """Извлекает число из запроса."""
        # Убираем пробелы в числах (10 000 -> 10000)
        query_no_spaces = query_lower.replace(' ', '')

        # Ищем числа
        numbers = re.findall(r'\d+', query_no_spaces)
        if numbers:
            return numbers[-1]  # Берем последнее число

        # Числа словами
        word_numbers = {
            'десять': '10',
            'сто': '100',
            'тысяч': '1000',
            'десять тысяч': '10000',
            'сто тысяч': '100000',
            'миллион': '1000000'
        }

        for word, num in word_numbers.items():
            if word in query_lower:
                return num

        return "1000"  # Значение по умолчанию


# Глобальный экземпляр
try:
    llm_client = LLMClient(skip_check=True)
except Exception as e:
    logger.warning(f"Failed to create LLM client: {e}")
    llm_client = None
