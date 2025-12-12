import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 500))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.1))

DATA_DIR = BASE_DIR / "data"
JSON_DATA_PATH = DATA_DIR / "videos.json"


def validate_config():
    """Проверяет что все необходимые параметры конфигурации присутствуют."""
    errors = []

    if not DB_PASSWORD:
        errors.append("DB_PASSWORD must be set in .env file")

    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN must be set in .env file")

    if errors:
        print("Configuration errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)


validate_config()

DATABASE_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "database": DB_NAME,
    "user": DB_USER,
    "password": DB_PASSWORD,
}

LLM_CONFIG = {
    "provider": LLM_PROVIDER,
    "model": LLM_MODEL,
    "base_url": LLM_BASE_URL,
    "max_tokens": LLM_MAX_TOKENS,
    "temperature": LLM_TEMPERATURE,
}
