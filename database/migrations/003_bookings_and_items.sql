-- 模組二：空間／物品預約借用模組

-- 1. 可借用物品資料表
CREATE TABLE IF NOT EXISTS borrowable_items (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_name text UNIQUE NOT NULL,
    description text,
    total_quantity integer NOT NULL DEFAULT 1 CHECK (total_quantity >= 0),
    is_active boolean NOT NULL DEFAULT true
);

-- 2. 空間借用申請資料表
CREATE TABLE IF NOT EXISTS bookings (
    booking_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id bigint NOT NULL REFERENCES rooms(room_id) ON DELETE RESTRICT,
    user_id bigint NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    booking_date date NOT NULL,
    start_time time NOT NULL,
    end_time time NOT NULL,
    purpose text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'checked_out', 'returned')),
    review_comment text,
    reviewed_by bigint REFERENCES users(user_id) ON DELETE SET NULL,
    reviewed_at timestamptz,
    checked_out_by bigint REFERENCES users(user_id) ON DELETE SET NULL,
    checked_out_at timestamptz,
    returned_by bigint REFERENCES users(user_id) ON DELETE SET NULL,
    returned_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_booking_time CHECK (start_time < end_time)
);

CREATE INDEX IF NOT EXISTS idx_bookings_room_date ON bookings (room_id, booking_date, status);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings (user_id);

-- 3. 借用物品明細資料表
CREATE TABLE IF NOT EXISTS booking_items (
    booking_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    booking_id bigint NOT NULL REFERENCES bookings(booking_id) ON DELETE CASCADE,
    item_id bigint NOT NULL REFERENCES borrowable_items(item_id) ON DELETE RESTRICT,
    quantity integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
    status text NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'checked_out', 'returned')),
    checked_out_at timestamptz,
    returned_at timestamptz,
    CONSTRAINT uq_booking_item UNIQUE (booking_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_booking_items_booking ON booking_items (booking_id);
