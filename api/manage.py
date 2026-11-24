import argparse
import os
import urllib.parse
from getpass import getpass

import psycopg
from app.db import ROOT, connect
from app.main import Credentials
from app.security import hash_password


def ensure_database():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return
    parsed = urllib.parse.urlparse(url)
    dbname = parsed.path.lstrip("/")
    if not dbname:
        return
    postgres_url = urllib.parse.urlunparse(parsed._replace(path="/postgres"))
    try:
        with psycopg.connect(url, connect_timeout=3):
            pass
    except psycopg.OperationalError as ex:
        if f'database "{dbname}" does not exist' in str(ex):
            try:
                with psycopg.connect(postgres_url, autocommit=True, connect_timeout=5) as conn:
                    conn.execute(f'CREATE DATABASE "{dbname}"')
                    print(f'已自動建立資料庫 "{dbname}"。')
            except Exception as e:
                print(f"嘗試建立資料庫失敗: {e}")


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("create-admin").add_argument("username")
    args = parser.parse_args()
    if args.command == "init":
        ensure_database()
    with connect() as db:
        if args.command == "init":
            migrations = sorted((ROOT / "database/migrations").glob("*.sql"))
            for file in [*migrations, ROOT / "database/seed.sql"]:
                db.execute(file.read_text(encoding="utf-8"))
            print("資料表與教室清單已就緒。")
            return
        account = Credentials(username=args.username, password=getpass("管理員密碼（至少 8 字元）: "))
        if getpass("再次輸入: ") != account.password:
            parser.exit(1, "兩次密碼不同。")
        row = db.execute(
            "INSERT INTO users(username,password_hash,role,approval_status) VALUES (%s,%s,'admin','approved') "
            "ON CONFLICT (username) DO NOTHING RETURNING user_id",
            (account.username, hash_password(account.password)),
        ).fetchone()
        if not row:
            parser.exit(1, "名稱已使用，請另選名稱。")
        print("管理員已建立。")


if __name__ == "__main__":
    main()
