import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from psycopg.rows import dict_row
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
)


@contextmanager
def connect():
    conn_fairy = engine.raw_connection()
    dbapi_conn = conn_fairy.dbapi_connection
    original_row_factory = dbapi_conn.row_factory
    dbapi_conn.row_factory = dict_row
    try:
        with dbapi_conn.transaction():
            yield dbapi_conn
    finally:
        dbapi_conn.row_factory = original_row_factory
        conn_fairy.close()

