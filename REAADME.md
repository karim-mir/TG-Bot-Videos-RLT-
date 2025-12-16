# Telegram-бот для работы с видео-данными
## Описание проекта
Telegram-бот для анализа статистики видео-контента. Бот принимает текстовые запросы на естественном языке, преобразует их в SQL-запросы к базе данных и возвращает результаты. Использует LLM (Ollama) для понимания естественного языка и преобразования запросов в структурированные SQL-команды.

### Ключевые возможности:
- 📊 Анализ статистики видео (просмотры, лайки, комментарии)
- 📈 Отслеживание роста просмотров по времени
- 🔍 Поиск и фильтрация видео по различным критериям
- 🏆 Рейтинги и топ-листы
- 🕐 Корректная обработка временных зон (UTC)

## Архитектура проекта

```
├── data/ # Данные проекта (конфигурация, JSON-файлы)
├── scripts/ # Вспомогательные скрипты
├── src/ # Исходный код приложения
│ ├── bot/ # Telegram-бот
│ │ ├── main.py # Запуск бота
│ │ └── handlers.py # Обработчики команд и сообщений
│ ├── core/ # Ядро приложения
│ │ ├── database.py # Работа с базой данных
│ │ └── llm_client.py # Клиент для работы с LLM (Ollama)
│ │ 
│ └── utils/ # Вспомогательные утилиты
│ └── config.py # Конфигурация приложения
│ 
├── tests/ # Тесты
├── docker-compose.yml # Docker Compose конфигурация
├── Dockerfile # Docker конфигурация для бота
├── pyproject.toml # Зависимости Python
├── .env.example # Шаблон переменных окружения
└── README.md # Документация
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
-- Таблица видео
CREATE TABLE videos (
    id UUID PRIMARY KEY,
    creator_id VARCHAR(255) NOT NULL,
    video_created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    views_count INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    reports_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Таблица снимков статистики (snapshots)
CREATE TABLE video_snapshots (
    id UUID PRIMARY KEY,
    video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
    views_count INTEGER DEFAULT 0,
    likes_count INTEGER DEFAULT 0,
    reports_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    delta_views_count INTEGER DEFAULT 0,
    delta_likes_count INTEGER DEFAULT 0,
    delta_reports_count INTEGER DEFAULT 0,
    delta_comments_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для ускорения запросов
CREATE INDEX idx_videos_creator_id ON videos(creator_id);
CREATE INDEX idx_videos_created_at ON videos(video_created_at);
CREATE INDEX idx_snapshots_video_id ON video_snapshots(video_id);
CREATE INDEX idx_snapshots_created_at ON video_snapshots(created_at);
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
