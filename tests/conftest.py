import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))


@pytest.fixture
def mock_config():
    """Фикстура для мока конфигурации."""
    with patch(
        "src.core.llm_client.LLM_CONFIG",
        {
            "model": "gemma3:4b",
            "base_url": "http://localhost:11434",
            "max_tokens": 100,
            "temperature": 0.1,
        },
    ):
        yield


@pytest.fixture(autouse=True)
def setup_logging():
    """Настройка логирования для тестов."""
    import logging

    logging.basicConfig(level=logging.WARNING)
