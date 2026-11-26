-- Own schema only. Safe to rerun with the existing manage.py init command.
CREATE TABLE IF NOT EXISTS courses (
    course_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 200),
    teacher_id bigint NOT NULL REFERENCES users(user_id),
    active boolean NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS schedule_preferences (
    preference_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id bigint NOT NULL REFERENCES courses ON DELETE CASCADE,
    room_id bigint NOT NULL REFERENCES rooms,
    start_date date NOT NULL,
    end_date date NOT NULL CHECK (end_date >= start_date AND end_date - start_date <= 366),
    weekday integer NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time time NOT NULL,
    end_time time NOT NULL CHECK (end_time > start_time)
);
CREATE TABLE IF NOT EXISTS schedule_series (
    series_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id bigint NOT NULL REFERENCES courses,
    teacher_id bigint NOT NULL REFERENCES users(user_id),
    room_id bigint NOT NULL REFERENCES rooms,
    start_date date NOT NULL,
    end_date date NOT NULL CHECK (end_date >= start_date AND end_date - start_date <= 366),
    weekday integer NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_time time NOT NULL,
    end_time time NOT NULL CHECK (end_time > start_time),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    active boolean NOT NULL DEFAULT true,
    created_by bigint NOT NULL REFERENCES users(user_id)
);
CREATE TABLE IF NOT EXISTS schedule_exceptions (
    exception_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    series_id bigint NOT NULL REFERENCES schedule_series,
    origin_date date NOT NULL,
    date date NOT NULL,
    room_id bigint NOT NULL REFERENCES rooms,
    start_time time NOT NULL,
    end_time time NOT NULL CHECK (end_time > start_time),
    UNIQUE(series_id, origin_date)
);
CREATE TABLE IF NOT EXISTS schedule_change_requests (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    series_id bigint NOT NULL REFERENCES schedule_series,
    requested_by bigint NOT NULL REFERENCES users(user_id),
    scope text NOT NULL CHECK (scope IN ('single','future')),
    effective_date date NOT NULL,
    new_date date NOT NULL,
    new_weekday integer NOT NULL CHECK (new_weekday BETWEEN 0 AND 6),
    room_id bigint NOT NULL REFERENCES rooms,
    start_time time NOT NULL,
    end_time time NOT NULL CHECK (end_time > start_time),
    original jsonb NOT NULL,
    series_version integer NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    note text NOT NULL DEFAULT '',
    review_note text NOT NULL DEFAULT '',
    reviewed_by bigint REFERENCES users(user_id),
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS schedule_series_course_idx ON schedule_series(course_id);
CREATE INDEX IF NOT EXISTS schedule_changes_status_idx ON schedule_change_requests(status);
