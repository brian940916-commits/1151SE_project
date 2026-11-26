"""Scheduling storage, ownership, and a shared transaction boundary."""
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone


def local_now():
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


def require_upcoming(events):
    now = local_now()
    if any(datetime.combine(e['date'],e['start_time']) < now for e in events):
        raise HTTPException(409,'不能新增、改派或調整已開始上課的安排；請建立新的課程保留歷史')


def validate_change_timing(db, series, change):
    old = db.execute('SELECT date,start_time FROM schedule_exceptions WHERE series_id=%s AND origin_date=%s',
                     (series['series_id'],change['effective_date'])).fetchone()
    old = old or {'date':change['effective_date'],'start_time':series['start_time']}
    require_upcoming([old,{'date':change['new_date'],'start_time':change['start_time']}])


def require_staff(user):
    if user['role'] not in ('teacher', 'admin'):
        raise HTTPException(403, '僅老師與管理員可使用排課功能')


def scheduling_lock(db):
    # Coarse lock intentionally serializes ALL scheduling mutations. Lock users
    # and rooms too, in stable order, for integration with a booking module.
    db.execute('SELECT pg_advisory_xact_lock(1151, 4)')


def lock_resources(db, teacher_ids, room_ids):
    db.execute('SELECT user_id FROM users WHERE user_id=ANY(%s) ORDER BY user_id FOR UPDATE',
               (sorted(set(teacher_ids)),)).fetchall()
    db.execute('SELECT room_id FROM rooms WHERE room_id=ANY(%s) ORDER BY room_id FOR UPDATE',
               (sorted(set(room_ids)),)).fetchall()


def get_course(db, course_id, user, active=False):
    require_staff(user)
    row = db.execute('SELECT * FROM courses WHERE course_id=%s', (course_id,)).fetchone()
    if not row:
        raise HTTPException(404, '課程不存在')
    if user['role'] != 'admin' and row['teacher_id'] != user['user_id']:
        raise HTTPException(403, '只能操作自己的課程')
    if active and not row['active']:
        raise HTTPException(409, '課程已停用')
    return row


def teacher(db, user_id):
    row = db.execute("SELECT user_id FROM users WHERE user_id=%s AND role='teacher' AND approval_status='approved'",
                     (user_id,)).fetchone()
    if not row:
        raise HTTPException(422, '必須指派已核准的老師')


def room(db, room_id, formal=False):
    row = db.execute('SELECT * FROM rooms WHERE room_id=%s', (room_id,)).fetchone()
    if not row:
        raise HTTPException(422, '教室不存在')
    if formal and row['is_schedulable'] is not True:
        raise HTTPException(409, '教室尚未確認可供排課')


def get_series(db, series_id, user):
    require_staff(user)
    row = db.execute('SELECT * FROM schedule_series WHERE series_id=%s', (series_id,)).fetchone()
    if not row:
        raise HTTPException(404, '正式課表不存在')
    get_course(db, row['course_id'], user, active=True)
    if not row['active']:
        raise HTTPException(409, '此課表已停用')
    return row


def insert_slot(db, table, course_id, values, extra=None):
    # table names/column names are INTERNAL constants, never request strings.
    from psycopg import sql
    data = dict(course_id=course_id, **values, **(extra or {}))
    return db.execute(sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING *').format(
        sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, data)),
        sql.SQL(',').join(sql.Placeholder() for _ in data)), tuple(data.values())).fetchone()
