CREATE TABLE IF NOT EXISTS users (
    user_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text UNIQUE NOT NULL,
    password_hash text NOT NULL,
    role text NOT NULL CHECK (role IN ('student','teacher','admin')),
    approval_status text NOT NULL CHECK (approval_status IN ('pending','approved','rejected'))
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash text PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    room_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_code text UNIQUE NOT NULL,
    name text NOT NULL,
    floor text NOT NULL,
    capacity integer CHECK (capacity > 0),
    is_bookable boolean,
    is_schedulable boolean
);
