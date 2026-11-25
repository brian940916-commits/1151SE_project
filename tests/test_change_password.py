"""測試密碼修改與設定密碼輸入兩次確認功能
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.auth import current_user
from app.db import connect
from app.main import (
    ChangePassword,
    Credentials,
    Registration,
    change_password,
    login,
    register,
)
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError


def test_password_features():
    print("=" * 60)
    print("測試：修改密碼與兩次密碼輸入確認防呆功能")
    print("=" * 60)

    # 1. 測試註冊時兩次密碼不一致防呆
    print(">>> 1. 測試註冊時兩次密碼不一致...")
    try:
        Registration(
            username="pw_test_user",
            password="InitialPass123",
            confirm_password="DifferentPass456",
            role="student",
        )
        assert False, "兩次密碼不同應拋出 ValidationError"
    except ValidationError as ex:
        assert "密碼與確認密碼不相符" in str(ex)
        print("✔ 註冊兩次密碼不同正確被攔截：", str(ex).split("\n")[0])

    # 2. 測試註冊兩次密碼一致
    print(">>> 2. 測試註冊兩次密碼一致成功...")
    with connect() as db:
        db.execute("DELETE FROM users WHERE username = 'pw_test_user'")

    reg = register(
        Registration(
            username="pw_test_user",
            password="InitialPass123",
            confirm_password="InitialPass123",
            role="student",
        )
    )
    assert reg["username"] == "pw_test_user"
    print("✔ 註冊成功，帳號已建立")

    # 3. 登入取得使用者物件
    print(">>> 3. 使用原密碼登入...")
    log_res = login(Credentials(username="pw_test_user", password="InitialPass123"))
    user_obj = current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=log_res["access_token"]))
    assert user_obj["username"] == "pw_test_user"
    print("✔ 登入成功取得憑證")

    # 4. 測試修改密碼時新密碼與確認密碼不一致
    print(">>> 4. 測試改密時新密碼與確認密碼不符...")
    try:
        ChangePassword(
            old_password="InitialPass123",
            new_password="NewSecurePass789",
            confirm_password="MismatchPass999",
        )
        assert False, "新密碼與確認密碼不同應拋出 ValidationError"
    except ValidationError as ex:
        assert "新密碼與確認新密碼不一致" in str(ex)
        print("✔ 改密兩次不同正確被攔截：", str(ex).split("\n")[0])

    # 5. 測試修改密碼時新密碼不可與舊密碼相同
    print(">>> 5. 測試新舊密碼相同...")
    try:
        ChangePassword(
            old_password="InitialPass123",
            new_password="InitialPass123",
            confirm_password="InitialPass123",
        )
        assert False, "新舊密碼相同應拋出 ValidationError"
    except ValidationError as ex:
        assert "新密碼不可與目前密碼相同" in str(ex)
        print("✔ 新舊密碼相同正確被攔截：", str(ex).split("\n")[0])

    # 6. 測試舊密碼輸入錯誤
    print(">>> 6. 測試目前舊密碼輸入錯誤...")
    req_wrong_old = ChangePassword(
        old_password="WrongOldPassword999",
        new_password="NewSecurePass789",
        confirm_password="NewSecurePass789",
    )
    try:
        change_password(req_wrong_old, user=user_obj)
        assert False, "舊密碼錯誤應拋出 HTTPException 400"
    except HTTPException as ex:
        assert ex.status_code == 400
        print(f"✔ 舊密碼錯誤正確被 400 攔截：{ex.detail}")

    # 7. 測試正常修改密碼
    print(">>> 7. 測試正常修改密碼...")
    req_valid = ChangePassword(
        old_password="InitialPass123",
        new_password="NewSecurePass789",
        confirm_password="NewSecurePass789",
    )
    res = change_password(req_valid, user=user_obj)
    assert "成功" in res["message"]
    print(f"✔ 密碼修改成功：{res['message']}")

    # 8. 驗證舊密碼已失效，無法登入
    print(">>> 8. 驗證舊密碼登入應失敗...")
    try:
        login(Credentials(username="pw_test_user", password="InitialPass123"))
        assert False, "舊密碼應不可再登入"
    except HTTPException as ex:
        assert ex.status_code == 401
        print("✔ 舊密碼無法登入（正確回傳 401 帳號或密碼錯誤）")

    # 9. 驗證新密碼可成功登入
    print(">>> 9. 驗證新密碼登入...")
    new_log = login(Credentials(username="pw_test_user", password="NewSecurePass789"))
    assert bool(new_log["access_token"])
    print("✔ 新密碼登入成功！")

    print("=" * 60)
    print("🎉 修改密碼與設定密碼輸入兩次確認功能全數驗證通過！")
    print("=" * 60)


if __name__ == "__main__":
    test_password_features()
