import asyncio
import datetime
import json
import logging
import sys
from pathlib import Path

from src.config import JSON_DATA_PATH
from src.core.database import db

sys.path.append(str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def load_data():
    """Загружает данные из JSON в базу данных."""

    try:
        await db.connect()

        await db.create_tables()
        logger.info("Таблицы созданы/проверены")

        await load_json_data()

        logger.info("✅ Данные успешно загружены!")

    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке данных: {e}")
        raise
    finally:
        await db.disconnect()


async def load_json_data():
    """Загружает данные из JSON."""

    if not JSON_DATA_PATH.exists():
        logger.error(f"Файл {JSON_DATA_PATH} не найден!")
        return

    logger.info(f"Чтение файла {JSON_DATA_PATH}...")

    with open(JSON_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    videos = data.get("videos", [])
    logger.info(f"Найдено {len(videos)} видео")

    video_count = 0
    snapshot_count = 0

    for video in videos:
        await insert_video(video)
        video_count += 1

        snapshots = video.get("snapshots", [])
        for snapshot in snapshots:
            await insert_snapshot(snapshot)
            snapshot_count += 1

        if video_count % 100 == 0:
            logger.info(f"Обработано {video_count} видео, {snapshot_count} снапшотов")

    logger.info(f"✅ Загружено: {video_count} видео, {snapshot_count} снапшотов")


async def insert_video(video: dict):
    """Вставить одно видео в БД."""
    sql = """
    INSERT INTO videos (id, creator_id, video_created_at, views_count,
                       likes_count, comments_count, reports_count,
                       created_at, updated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (id) DO NOTHING
    """

    try:

        video_created_at = datetime.datetime.fromisoformat(
            video["video_created_at"].replace("Z", "+00:00")
        )
        created_at = datetime.datetime.fromisoformat(
            video["created_at"].replace("Z", "+00:00")
        )
        updated_at = datetime.datetime.fromisoformat(
            video["updated_at"].replace("Z", "+00:00")
        )

        await db.pool.execute(
            sql,
            video["id"],
            video["creator_id"],
            video_created_at,
            video["views_count"],
            video["likes_count"],
            video["comments_count"],
            video["reports_count"],
            created_at,
            updated_at,
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при вставке видео {video['id']}: {e}")


async def insert_snapshot(snapshot: dict):
    """Вставить один снапшот в БД."""
    sql = """
    INSERT INTO video_snapshots (id, video_id, views_count, likes_count,
                                comments_count, reports_count,
                                delta_views_count, delta_likes_count,
                                delta_comments_count, delta_reports_count,
                                created_at, updated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    ON CONFLICT (id) DO NOTHING
    """

    try:

        created_at = datetime.datetime.fromisoformat(
            snapshot["created_at"].replace("Z", "+00:00")
        )
        updated_at = datetime.datetime.fromisoformat(
            snapshot["updated_at"].replace("Z", "+00:00")
        )

        await db.pool.execute(
            sql,
            snapshot["id"],
            snapshot["video_id"],
            snapshot["views_count"],
            snapshot["likes_count"],
            snapshot["comments_count"],
            snapshot["reports_count"],
            snapshot["delta_views_count"],
            snapshot["delta_likes_count"],
            snapshot["delta_comments_count"],
            snapshot["delta_reports_count"],
            created_at,
            updated_at,
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при вставке снапшота {snapshot['id']}: {e}")


if __name__ == "__main__":
    asyncio.run(load_data())
