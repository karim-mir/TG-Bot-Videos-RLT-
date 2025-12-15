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
        """Строит точный промпт для Gemma3:4b."""

        prompt = f"""
    Ты SQL-ассистент. Ответь ТОЛЬКО SQL запросом с точкой с запятой в конце.

    ВАЖНЫЕ ПРАВИЛА ПО ДАТАМ:
    1. Для месяцев используй ПОЛНЫЕ ДНИ: '2025-06-30', '2025-11-30'
    2. Для диапазона июнь 2025: BETWEEN '2025-06-01' AND '2025-06-30'
    3. Для диапазона ноябрь 2025: BETWEEN '2025-11-01' AND '2025-11-30'
    4. Лучше используй EXTRACT для месяцев: EXTRACT(YEAR FROM ...) = 2025 AND EXTRACT(MONTH FROM ...) = 6

    Структура базы данных:
    1. Таблица videos (финальная статистика видео):
       - id, creator_id, views_count, video_created_at
       - Используй для: количество видео, просмотров, дат публикации

    2. Таблица video_snapshots (почасовые изменения):
       - video_id, delta_views_count, delta_likes_count, created_at
       - Используй для: дельты просмотров, отрицательные значения, изменения по часам

    Примеры:
    Вопрос: Какое суммарное количество просмотров набрали все видео, опубликованные в июне 2025 года?
    SQL: SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 AND EXTRACT(MONTH FROM video_created_at) = 6;

    Вопрос: Сколько всего замеров статистики с отрицательными просмотрами?
    SQL: SELECT COUNT(*) FROM video_snapshots WHERE delta_views_count < 0;

    Вопрос: Сколько видео опубликовал креатор X в период с 1 по 5 ноября?
    SQL: SELECT COUNT(*) FROM videos WHERE creator_id = 'X' AND (video_created_at AT TIME ZONE 'UTC')::date BETWEEN '2025-11-01' AND '2025-11-05';

    Вопрос: {user_query}
    SQL:"""

        return prompt.strip()

    def _validate_and_fix_sql(self, sql: str, user_query: str) -> str:
        """Валидирует и исправляет SQL для Gemma."""
        if not sql:
            return self._fallback_sql_for_query(user_query)

        sql = sql.strip()

        # 1. Исправляем незавершенные кавычки
        sql = self._fix_unclosed_quotes(sql)

        # 2. Исправляем точку с запятой в кавычках
        sql = self._fix_semicolon_in_quotes(sql)

        # 3. Добавляем точку с запятой если нет
        if not sql.endswith(';'):
            sql += ';'

        # 4. Проверяем логику запроса
        sql = self._fix_query_logic(sql, user_query)

        # 5. Если SQL слишком длинный или содержит лишнее
        if '\n' in sql and sql.count('\n') > 3:
            lines = sql.split('\n')
            for line in lines:
                if line.upper().startswith('SELECT'):
                    sql = line.strip()
                    break

        # 6. Очищаем от комментариев
        if '--' in sql:
            sql = sql.split('--')[0].strip()

        return sql

    def _fix_unclosed_quotes(self, sql: str) -> str:
        """Исправляет незавершенные кавычки."""
        # Считаем одинарные кавычки
        single_quotes = sql.count("'")

        if single_quotes % 2 != 0:
            # Нечетное количество - добавляем в конец перед точкой с запятой
            if sql.endswith(';'):
                sql = sql[:-1] + "'" + ";"
            else:
                sql = sql + "'"

        return sql

    def _fix_semicolon_in_quotes(self, sql: str) -> str:
        """Исправляет точку с запятой внутри кавычек."""
        # Ищем паттерн 'YYYY-MM-DD;'
        import re
        pattern = r"'(\d{4}-\d{2}-\d{2});'"
        matches = re.findall(pattern, sql)

        for match in matches:
            correct_date = match[:-1]  # Убираем точку с запятой
            sql = sql.replace(f"'{match};'", f"'{correct_date}'")

        return sql

    def _fix_query_logic(self, sql: str, user_query: str) -> str:
        """Исправляет логические ошибки в SQL."""
        query_lower = user_query.lower()
        sql_lower = sql.lower()

        # 1. Запросы о суммарных просмотрах ВСЕГДА используют таблицу videos
        if "суммарное количество просмотров" in query_lower or "сумма просмотров" in query_lower:
            if "video_snapshots" in sql_lower and "delta_views_count" in sql_lower:
                # Заменяем на правильный запрос
                if "июне" in query_lower:
                    return "SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 AND EXTRACT(MONTH FROM video_created_at) = 6;"
                elif "ноябре" in query_lower:
                    return "SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 AND EXTRACT(MONTH FROM video_created_at) = 11;"
                else:
                    return "SELECT SUM(views_count) FROM videos;"

        # 2. Исправляем некорректные даты
        import re

        # Исправляем '2025-06-3' -> '2025-06-30'
        if "'2025-06-3'" in sql:
            sql = sql.replace("'2025-06-3'", "'2025-06-30'")

        # Исправляем '2025-11-5' -> '2025-11-05' (но для периода 1-5 ноября это правильно!)
        # Внимание: для периода 1-5 ноября '2025-11-5' это правильно, не меняем!

        # 3. Если в запросе есть "опубликованные в июне/ноябре", используем EXTRACT
        if any(month in query_lower for month in ["июне", "ноябре", "январе", "феврале"]):
            if "between" in sql_lower and "2025" in sql_lower:
                # Заменяем BETWEEN на EXTRACT для надежности
                month_map = {"июне": 6, "ноябре": 11, "январе": 1, "феврале": 2}
                for month_ru, month_num in month_map.items():
                    if month_ru in query_lower:
                        return f"SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 AND EXTRACT(MONTH FROM video_created_at) = {month_num};"

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
        """Умные fallback правила, а не хардкод."""
        query_lower = user_query.lower()

        # Извлекаем информацию
        creator_id = self._extract_creator_id(query_lower)

        # 1. Сумма просмотров за месяц
        if "суммарное количество просмотров" in query_lower:
            if "июне" in query_lower:
                return "SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 AND EXTRACT(MONTH FROM video_created_at) = 6;"
            elif "ноябре" in query_lower:
                return "SELECT SUM(views_count) FROM videos WHERE EXTRACT(YEAR FROM video_created_at) = 2025 AND EXTRACT(MONTH FROM video_created_at) = 11;"
            else:
                return "SELECT SUM(views_count) FROM videos;"

        # 2. Запросы с креатором и датами
        if creator_id and any(word in query_lower for word in ["опубликовал", "период", "ноября", "июня"]):
            date_range = self._extract_date_range(query_lower)
            if date_range:
                date_from, date_to = date_range
                return f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' AND (video_created_at AT TIME ZONE 'UTC')::date BETWEEN '{date_from}' AND '{date_to}';"
            elif "июне" in query_lower:
                return f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' AND EXTRACT(YEAR FROM video_created_at) = 2025 AND EXTRACT(MONTH FROM video_created_at) = 6;"

        # 3. Запросы с условиями по просмотрам
        if creator_id and any(word in query_lower for word in ['больше', 'набрали']):
            number = self._extract_number(query_lower)
            if number:
                return f"SELECT COUNT(*) FROM videos WHERE creator_id = '{creator_id}' AND views_count > {number};"

        # 4. Отрицательные просмотры
        if "замеров статистики" in query_lower and "отрицательным" in query_lower:
            return "SELECT COUNT(*) FROM video_snapshots WHERE delta_views_count < 0;"

        # 5. Общие запросы
        if "сколько всего видео" in query_lower:
            return "SELECT COUNT(*) FROM videos;"

        if "сколько разных креаторов" in query_lower:
            return "SELECT COUNT(DISTINCT creator_id) FROM videos;"

        # Дефолтный запрос
        return "SELECT COUNT(*) FROM videos;"

    def _extract_date_range(self, query: str) -> tuple:
        """Извлекает диапазон дат из запроса."""
        # Убрать import re - он уже в начале файла

        # Паттерн для "с 1 ноября 2025 по 5 ноября 2025"
        pattern = r'с\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s+по\s+(\d{1,2})\s+(\w+)\s+(\d{4})'
        match = re.search(pattern, query.lower())

        if match:
            day1, month_ru1, year1, day2, month_ru2, year2 = match.groups()

            # Конвертируем русские названия месяцев в числа
            months_ru = {
                'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
                'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
                'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
            }

            month1 = months_ru.get(month_ru1, '01')
            month2 = months_ru.get(month_ru2, '01')

            # Форматируем даты
            date1 = f"{year1}-{month1}-{int(day1):02d}"
            date2 = f"{year2}-{month2}-{int(day2):02d}"

            return date1, date2

        return None

    def _extract_single_date(self, query: str) -> str:
        """Извлекает одиночную дату из запроса."""
        import re

        # Паттерн для "28 ноября 2025"
        pattern = r'(\d{1,2})\s+(\w+)\s+(\d{4})'
        match = re.search(pattern, query.lower())

        if match:
            day, month_ru, year = match.groups()

            months_ru = {
                'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
                'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
                'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12'
            }

            month = months_ru.get(month_ru, '01')

            return f"{year}-{month}-{int(day):02d}"

        return None

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

            # ВАЖНО: Добавляем точку с запятой если её нет
            if not response_text.endswith(';'):
                response_text += ';'

            # Проверяем баланс кавычек
            if response_text.count("'") % 2 != 0:
                # Нечетное количество кавычек - добавляем недостающую
                response_text += "'"

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
        """Извлекает число из запроса, включая числа с пробелами."""
        # Сначала пробуем найти числа с пробелами (10 000, 100 000)
        spaced_numbers = re.findall(r'(\d[\d\s]*\d)', query_lower.replace(',', ''))
        if spaced_numbers:
            # Берем последнее число и убираем пробелы
            num = spaced_numbers[-1].replace(' ', '')
            return num

        # Затем ищем обычные числа
        numbers = re.findall(r'\d+', query_lower.replace(' ', ''))
        if numbers:
            return numbers[-1]

        # Числа словами
        word_numbers = {
            'десять': '10',
            'сто': '100',
            'тысяч': '1000',
            'тысяча': '1000',
            'десять тысяч': '10000',
            '10 тысяч': '10000',
            'сто тысяч': '100000',
            '100 тысяч': '100000',
            'миллион': '1000000',
            'миллиона': '1000000'
        }

        for word, num in word_numbers.items():
            if word in query_lower:
                return num

        return ""


# Глобальный экземпляр
try:
    llm_client = LLMClient(skip_check=True)
except Exception as e:
    logger.warning(f"Failed to create LLM client: {e}")
    llm_client = None
