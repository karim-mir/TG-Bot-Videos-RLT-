import asyncio
import os
import sys

from src.core.database import db

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def test_database():
    """Тест подключения к базе данных."""

    try:
        print("1. Подключение к базе данных...")
        await db.connect()
        print("   ✅ Успешно")

        print("2. Создание таблиц...")
        await db.create_tables()
        print("   ✅ Таблицы созданы")

        print("3. Проверка подключения...")
        result = await db.execute_scalar("SELECT 1")
        print(f"   ✅ Результат тестового запроса: {result}")

        print("4. Отключение от базы...")
        await db.disconnect()
        print("   ✅ Успешно отключено")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_database())
