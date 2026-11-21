import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=5)
