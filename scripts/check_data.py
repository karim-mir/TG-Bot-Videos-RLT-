import asyncio
import sys
from pathlib import Path

from src.core.database import db

sys.path.append(str(Path(__file__).parent.parent))


async def check_data():
    """Проверяет загруженные данные."""
    try:
        await db.connect()

        print("Проверка загруженных данных...")
        print("=" * 50)

        videos_count = await db.execute_scalar("SELECT COUNT(*) FROM videos")
        print(f"Всего видео в базе: {videos_count} ")

        snapshots_count = await db.execute_scalar(
            "SELECT COUNT(*) FROM video_snapshots"
        )
        print(f"Всего снапшотов в базе: {snapshots_count}")

        avg_snapshots = await db.execute_scalar(
            "SELECT AVG(snapshots_count) FROM (SELECT video_id, COUNT(*) as snapshots_count FROM video_snapshots "
            "GROUP BY video_id) as subquery"
        )
        print(f"В среднем снапшотов на видео: {avg_snapshots:.1f}")

        print("\n Тестовые запросы из задания:")

        print(f"1. 'Сколько всего видео есть в системе?' = {videos_count}")

        videos_over_1000 = await db.execute_scalar(
            "SELECT COUNT(*) FROM videos WHERE views_count > 1000"
        )
        print(
            f"2. 'Сколько видео набрало больше 1000 просмотров?' = {videos_over_1000}"
        )

        unique_creators = await db.execute_scalar(
            "SELECT COUNT(DISTINCT creator_id) FROM videos"
        )
        print(f"3. 'Сколько разных креаторов?' = {unique_creators}")

        print("\n Пример запроса с датой:")
        sample_date = await db.execute_scalar(
            "SELECT DATE(created_at) FROM video_snapshots LIMIT 1"
        )
        if sample_date:
            print(f"пример даты из данных: {sample_date}")
            views_growth = await db.execute_scalar(
                f"SELECT SUM(delta_views_count) FROM video_snapshots WHERE DATE(created_at) = '{sample_date}'"
            )
            print(
                f"'На сколько просмотров выросли все видео {sample_date}?' = {views_growth or 0}"
            )

        print("\n Топ-5 видео по просмотрам:")
        top_videos = await db.execute_query(
            "SELECT id, views_count, creator_id FROM videos ORDER BY views_count DESC LIMIT 5"
        )

        for i, video in enumerate(top_videos, 1):
            print(
                f"{i}. ID: {video['id'][:12]}..., Creator: {video['creator_id'][:8]}..., Views: {video['views_count']}"
            )

        await db.disconnect()
        print("\n✅ Проверка завершена успешно!")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_data())
