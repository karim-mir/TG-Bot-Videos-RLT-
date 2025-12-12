import asyncio
import sys
from pathlib import Path

from src.core.database import db
from src.bot.handlers import parse_natural_query, parse_date

sys.path.append(str(Path(__file__).parent.parent))


async def test_query():
    await db.connect()

    query = "Сколько видео опубликовал креатор с id 8b76e572635b400c9052286a56176e03 в период с 1 ноября 2025 по 5 ноября 2025 включительно?"

    print(f"Запрос: {query}")
    sql, params = parse_natural_query(query)
    print(f"SQL: {sql}")
    print(f"Params: {params}")

    if sql and params:
        param_values = list(params.values())
        result = await db.execute_scalar(sql, *param_values)
        print(f"Результат: {result}")

        # Также выполним запрос вручную для проверки
        print("\nПроверочные запросы:")

        # 1. Все видео этого креатора
        all_videos = await db.execute_scalar(
            "SELECT COUNT(*) FROM videos WHERE creator_id = $1",
            '8b76e572635b400c9052286a56176e03'
        )
        print(f"Всего видео у креатора: {all_videos}")

        # 2. Видео за период
        test_sql = """
            SELECT id, video_created_at 
            FROM videos 
            WHERE creator_id = $1 
            AND DATE(video_created_at) BETWEEN $2 AND $3
            ORDER BY video_created_at
        """
        videos = await db.execute_query(test_sql, '8b76e572635b400c9052286a56176e03', '2025-11-01', '2025-11-05')
        print(f"Видео за период (найдено {len(videos)}):")
        for video in videos[:10]:  # первые 10
            print(f"  ID: {video['id'][:12]}..., Дата: {video['video_created_at']}")

        # 3. Проверим даты всех видео этого креатора
        check_sql = """
            SELECT DATE(video_created_at) as date, COUNT(*) as count
            FROM videos 
            WHERE creator_id = $1
            GROUP BY DATE(video_created_at)
            ORDER BY date
        """
        dates = await db.execute_query(check_sql, '8b76e572635b400c9052286a56176e03')
        print(f"\nРаспределение видео по датам:")
        for date_info in dates:
            print(f"  {date_info['date']}: {date_info['count']} видео")

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(test_query())
