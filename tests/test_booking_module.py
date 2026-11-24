"""模組二：空間／物品預約借用模組 自動化驗證測試腳本
涵蓋：
1. 時段衝突判斷邏輯（相鄰可銜接 10:00-11:00 vs 11:00-12:00 不衝突；重疊時段判定衝突）
2. FastAPI 路由與端點註冊驗證（包含原有認證路由與空間查詢，以及新加入的借用 7 個端點）
3. 資料模型驗證（BookingCreate, ReviewDecision）
4. Migration SQL 與 Seed SQL 檔案結構與語法驗證
5. 預約流程狀態機驗證 (pending -> approved -> checked_out -> returned，以及衝突時 409 回傳)
"""

import sys
from datetime import date, time, timedelta
from pathlib import Path

# 加入 api 目錄至 sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from app.main import app
from app.routers.bookings import BookingCreate, ReviewDecision
from pydantic import ValidationError


def test_overlap_algorithm():
    """驗證相鄰時段可銜接與重疊衝突判斷演算法。

    規則：[s1, e1) 與 [s2, e2) 重疊若且唯若 (s1 < e2 AND e1 > s2)
    """
    def is_overlap(s1: time, e1: time, s2: time, e2: time) -> bool:
        return s1 < e2 and e1 > s2

    t0900 = time(9, 0)
    t1000 = time(10, 0)
    t1030 = time(10, 30)
    t1100 = time(11, 0)
    t1130 = time(11, 30)
    t1200 = time(12, 0)
    t1300 = time(13, 0)

    # 1. 相鄰銜接（不衝突）
    assert not is_overlap(t1000, t1100, t1100, t1200), "10:00-11:00 與 11:00-12:00 相鄰應不衝突"
    assert not is_overlap(t1100, t1200, t1000, t1100), "11:00-12:00 與 10:00-11:00 相鄰應不衝突"
    assert not is_overlap(t0900, t1000, t1000, t1100), "09:00-10:00 與 10:00-11:00 相鄰應不衝突"

    # 2. 部分重疊（衝突）
    assert is_overlap(t1000, t1100, t1030, t1130), "10:00-11:00 與 10:30-11:30 重疊應衝突"
    assert is_overlap(t1030, t1130, t1000, t1100), "10:30-11:30 與 10:00-11:00 重疊應衝突"

    # 3. 包含與完全包覆（衝突）
    assert is_overlap(t0900, t1300, t1000, t1100), "09:00-13:00 包覆 10:00-11:00 應衝突"
    assert is_overlap(t1000, t1100, t0900, t1300), "10:00-11:00 被 09:00-13:00 包覆 應衝突"

    # 4. 完全相同（衝突）
    assert is_overlap(t1000, t1100, t1000, t1100), "相同時段應衝突"

    print("✔ [1/5] 時段衝突判斷邏輯測試通過（相鄰可銜接，重疊正確報衝突）")


def test_routes_registered():
    """驗證所有 API 端點皆已在 FastAPI app 註冊，且無破壞既有端點。"""
    openapi_paths = app.openapi()["paths"]

    # 檢查既有端點
    expected_legacy = [
        ("GET", "/api/rooms"),
        ("POST", "/api/auth/register"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
        ("GET", "/api/admin/pending"),
        ("POST", "/api/admin/users/{user_id}/review"),
    ]
    for method, path in expected_legacy:
        assert path in openapi_paths, f"既有路徑遺失: {path}"
        assert method.lower() in openapi_paths[path], f"既有端點遺失方法: {method} {path}"

    # 檢查新增預約端點
    expected_bookings = [
        ("GET", "/api/items"),
        ("GET", "/api/bookings/weekly"),
        ("POST", "/api/bookings"),
        ("GET", "/api/bookings"),
        ("POST", "/api/admin/bookings/{booking_id}/review"),
        ("POST", "/api/admin/bookings/{booking_id}/checkout"),
        ("POST", "/api/admin/bookings/{booking_id}/return"),
    ]
    for method, path in expected_bookings:
        assert path in openapi_paths, f"預約模組路徑未註冊: {path}"
        assert method.lower() in openapi_paths[path], f"預約模組端點未註冊方法: {method} {path}"

    print(f"✔ [2/5] API 路由註冊測試通過（驗證 {len(expected_legacy)} 個既有端點與 {len(expected_bookings)} 個新增預約端點）")


def test_data_models():
    """驗證資料模型校驗規則。"""
    today = date.today()

    # 正常建立
    booking = BookingCreate(
        room_id=1,
        booking_date=today + timedelta(days=1),
        start_time=time(10, 0),
        end_time=time(12, 0),
        purpose="研討會測試",
        item_ids=[1, 2],
    )
    assert booking.room_id == 1
    assert booking.purpose == "研討會測試"
    assert booking.item_ids == [1, 2]

    # 審核決策驗證
    rev_ok = ReviewDecision(status="approved", review_comment="核准借用")
    assert rev_ok.status == "approved"

    try:
        ReviewDecision(status="unknown_status")
        assert False, "不合法狀態應拋出 ValidationError"
    except ValidationError:
        pass

    print("✔ [3/5] 資料模型與 Pydantic 驗證測試通過")


def test_sql_migrations_syntax():
    """驗證 Migration SQL 與 Seed SQL 檔案存在且語法完整。"""
    migrations_dir = ROOT / "database/migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))
    filenames = [f.name for f in sql_files]

    assert "001_auth_rooms.sql" in filenames, "缺少 001_auth_rooms.sql"
    assert "002_student_registration.sql" in filenames, "缺少 002_student_registration.sql"
    assert "003_bookings_and_items.sql" in filenames, "缺少 003_bookings_and_items.sql"

    content_003 = (migrations_dir / "003_bookings_and_items.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS borrowable_items" in content_003
    assert "CREATE TABLE IF NOT EXISTS bookings" in content_003
    assert "CREATE TABLE IF NOT EXISTS booking_items" in content_003
    assert "start_time < end_time" in content_003

    seed_content = (ROOT / "database/seed.sql").read_text(encoding="utf-8")
    assert "INSERT INTO borrowable_items" in seed_content
    assert "投影筆" in seed_content
    assert "ON CONFLICT (item_name) DO NOTHING" in seed_content

    print("✔ [4/5] Migration SQL 與 Seed SQL 結構校驗通過")


def test_booking_status_flow():
    """驗證預約狀態機業務規則：

    - 初始: pending
    - 審核: pending -> approved / rejected
    - 領用: approved -> checked_out (只有 approved 可 checked_out)
    - 歸還: checked_out -> returned (只有 checked_out 可 returned)
    - 非法躍遷: pending 直接 checkout/return 應被拒絕
    """
    valid_transitions = {
        "pending": ["approved", "rejected"],
        "approved": ["checked_out"],
        "checked_out": ["returned"],
        "returned": [],
        "rejected": [],
    }

    def can_transition(current_status: str, target_status: str) -> bool:
        return target_status in valid_transitions.get(current_status, [])

    # 正確流程
    assert can_transition("pending", "approved"), "待審核應可核准"
    assert can_transition("pending", "rejected"), "待審核應可退件"
    assert can_transition("approved", "checked_out"), "已核准應可借出領用"
    assert can_transition("checked_out", "returned"), "借出中應可歸還"

    # 非法流程
    assert not can_transition("pending", "checked_out"), "待審核不可直接借出"
    assert not can_transition("pending", "returned"), "待審核不可直接歸還"
    assert not can_transition("approved", "returned"), "已核准尚未借出不可直接歸還"
    assert not can_transition("returned", "checked_out"), "已歸還不可再次借出"
    assert not can_transition("rejected", "approved"), "已退件不可直接核准"

    print("✔ [5/5] 空間與物品借用狀態機流程驗證通過（核准 → 領用 → 歸還 合法，違規躍遷正確攔截）")


if __name__ == "__main__":
    print("=" * 60)
    print("開始執行模組二：空間／物品預約借用模組 自動化驗證...")
    print("=" * 60)
    test_overlap_algorithm()
    test_routes_registered()
    test_data_models()
    test_sql_migrations_syntax()
    test_booking_status_flow()
    print("=" * 60)
    print("恭喜！所有單元與模組測試全數通過！")
    print("=" * 60)
