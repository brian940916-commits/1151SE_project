import argparse
from getpass import getpass

from app.db import ROOT, connect
from app.accounts import Credentials
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    commands.add_parser("create-admin").add_argument("username")
    args = parser.parse_args()
    with connect() as db:
        if args.command == "init":
            migrations = sorted((ROOT / "database/migrations").glob("*.sql"))
            for file in [*migrations, ROOT / "database/seed.sql", ROOT / "database/room_profiles.sql"]:
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
