import asyncio
import json
import logging
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from src.core.database import db
from src.config import JSON_DATA_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
