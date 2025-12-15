# Telegram-бот для работы с видео-данными
## Описание проекта
### Telegram-бот, который принимает текстовые запросы пользователей, преобразует их в структурированные SQL-запросы или код для работы с базой данных видео-контента, используя LLM (Large Language Model) для понимания естественного языка.

#### Архитектура проекта

```project/
├── data/              # Данные проекта (конфигурация, JSON-файлы)
├── scripts/           # Вспомогательные скрипты
├── src/               # Исходный код приложения
│   ├── bot/           # Telegram-бот
│   ├── core/          # Ядро приложения (БД, LLM-клиент)
│   └── utils/         # Вспомогательные утилиты
├── tests/             # Тесты
└── ... конфигурационные файлы
```
#### Подход к преобразованию текстовых запросов

Пользователь отправляет текстовый запрос на естественном языке → LLM анализирует запрос и преобразует его в:

- SQL-запрос (если требуется работа с базой данных)
- Код на Python (для сложных операций)
- Структурированный запрос к API/сервисам

#### Описание схемы данных для LLM
При работе с LLM используется следующий подход:

- Контекст схемы БД передается в системном промпте

Примеры таблиц и полей:
```
{
  "videos": {
    "id": "integer",
    "title": "string",
    "description": "text",
    "duration_seconds": "integer",
    "upload_date": "datetime",
    "category": "string",
    "views": "integer",
    "likes": "integer"
  },
  "users": {
    "id": "integer",
    "username": "string",
    "subscription_level": "string"
  }
}
```
Промпт-шаблон:

```SYSTEM_PROMPT = """
Ты - ассистент, преобразующий текстовые запросы в SQL.
Доступные таблицы: {tables_description}
Правила:
1. Генерируй только SQL без пояснений
2. Используй правильные типы данных
3. Для дат используй формат YYYY-MM-DD
4. Обрабатывай NULL-значения
```

Примеры:
```
Запрос: "Покажи 10 самых популярных видео"
SQL: SELECT title, views FROM videos ORDER BY views DESC LIMIT 10
"""
```

## Быстрый запуск с Docker
### Предварительные требования

- Docker и Docker Compose
- Telegram Bot Token

#### Шаги запуска
- Клонируйте репозиторий
```
- git clone https://github.com/karim-mir/TG-Bot-Videos-RLT-
```
- Настройте переменные окружения
```
env.example .env
```
- Отредактируйте .env файл, добавьте ваш Telegram токен

- Запустите контейнеры

```
docker-compose up --build
```
- Проверьте работоспособность
```
docker-compose ps
```

- Запустите бота

```
poetry run python src/bot/main.py
```
## Настройка Telegram-бота
- Получение токена
1. Откройте Telegram и найдите @BotFather

2. Создайте нового бота: /newbot

3. Скопируйте полученный токен

4. Установка токена в файле .env
```
TELEGRAM_BOT_TOKEN=ваш_токен
LLM_MODEL=gemma3:4b
DATABASE_URL=sqlite:///data/videos.db
```

### Примеры запросов к боту
```
Пользовательский запрос	                                Преобразованный SQL/код
"Покажи 5 последних видео"	                        SELECT * FROM videos ORDER BY upload_date DESC LIMIT 5
"Самые популярные видео в категории 'Образование'"	SELECT title, views FROM videos WHERE category = 'Образование' ORDER BY views DESC
"Статистика по загруженным видео"	                SELECT category, COUNT(*) as count, AVG(views) as avg_views FROM videos GROUP BY category
```
### Тестирование
- Запуск всех тестов
```
poetry run python run_tests.py
```
- Отдельные тесты

`1. Тесты базы данных`
```
poetry run pytest tests/test_database.py
```

`2. Тесты LLM`
```
poetry run pytest tests/test_llm.py
```

`3. Тесты запросов`
```
poetry run pytest tests/test_query.py
```

## Структура кода
### Ключевые модули:
`src/bot/handlers.py - обработчики команд Telegram`

`src/bot/main.py - запуск бота`

`core/database.py - работа с базой данных`

`core/llm_client.py - клиент для работы с LLM`

`utils/config.py - конфигурация приложения`
