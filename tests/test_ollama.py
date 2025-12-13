import time
from src.core.llm_client import llm_client


def test_gemma():
    """Тестирование работы Gemma."""
    if llm_client:
        test_queries = [
            "Сколько всего видео есть в системе?",
            "Сколько видео набрало больше 1000 просмотров?",
            "Сколько всего есть замеров статистики с отрицательными просмотрами?",
            "Сколько разных креаторов?",
            "Сколько видео у креатора с id abc123 вышло с 1 ноября 2025 по 5 ноября 2025?",
        ]

        for query in test_queries:
            print(f"\n{'=' * 60}")
            print(f"Запрос: {query}")
            print(f"{'=' * 60}")

            try:
                start_time = time.time()
                sql = llm_client.generate_sql_from_natural_language(query)
                elapsed = time.time() - start_time

                print(f"SQL: {sql}")
                print(f"Время: {elapsed:.2f} сек")
            except Exception as e:
                print(f"Ошибка: {e}")
    else:
        print("LLM клиент не инициализирован")


if __name__ == "__main__":
    test_gemma()
