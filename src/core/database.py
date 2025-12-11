import asyncpg
import logging
from typing import List, Dict, Any, Optional
from src.config import DATABASE_CONFIG


logger = logging.getLogger(__name__)

class Database:
    """Класс для работы с базой данных PostgreSQL."""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Подключается к БД."""

        try:
            self.pool = await asyncpg.create_pool(
                host=DATABASE_CONFIG["host"],
                port=DATABASE_CONFIG["port"],
                database=DATABASE_CONFIG["database"],
                user=DATABASE_CONFIG["user"],
                password=DATABASE_CONFIG["password"],
                min_size=1,
                max_size=10
            )
            logger.info("Подключение к базе данных установлено")
        except Exception as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
            raise

    async def disconnect(self):
        """Отключение от базы данных."""

        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Отключение от базы данных")

    async def create_tables(self):
        """Создает таблицы, если они не существуют."""

        async with self.pool.acquire() as conn:

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS videos (
                id VARCHAR(36) PRIMARY KEY,
                    creator_id VARCHAR(32) NOT NULL,
                    video_created_at TIMESTAMPTZ NOT NULL,
                    views_count INTEGER DEFAULT 0,
                    likes_count INTEGER DEFAULT 0,
                    comments_count INTEGER DEFAULT 0,
                    reports_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL
                )
            ''')

            await conn.execute('''
            CREATE TABLE IF NOT EXISTS video_snapshots (
                    id VARCHAR(50) PRIMARY KEY,
                    video_id VARCHAR(36) NOT NULL,
                    views_count INTEGER DEFAULT 0,
                    likes_count INTEGER DEFAULT 0,
                    comments_count INTEGER DEFAULT 0,
                    reports_count INTEGER DEFAULT 0,
                    delta_views_count INTEGER DEFAULT 0,
                    delta_likes_count INTEGER DEFAULT 0,
                    delta_comments_count INTEGER DEFAULT 0,
                    delta_reports_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    FOREIGN KEY (video_id) REFERENCES videos(id) ON DELETE CASCADE
                )
            ''')

            await self._create_indexes(conn)

        logger.info("Таблицы созданы или уже существуют.")

    async def _create_indexes(self, conn):
        """Создает индексы для оптимизации запросов."""

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_videos_creator_id ON videos(creator_id)",
            "CREATE INDEX IF NOT EXISTS idx_videos_created_at ON videos(video_created_at)",
            "CREATE INDEX IF NOT EXISTS idx_videos_views ON videos(views_count)",
            "CREATE INDEX IF NOT EXISTS idx_snapshots_video_id ON video_snapshots(video_id)",
            "CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON video_snapshots(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_snapshots_video_created ON video_snapshots(video_id, created_at)"
        ]

        for index_sql in indexes:
            await conn.execute(index_sql)

    async def execute_query(self, sql: str, *args) -> List[Dict[str, Any]]:
        """Выполняет SQL запросы и возвращает результат."""

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
            return [dict(row) for row in rows]

    async def execute_scalar(self, sql: str, *args) -> Any:
        """Выполняет SQL запрос и возвращает скалярное значение (одно число)."""
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql, *args)

db = Database()
