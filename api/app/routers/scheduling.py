from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from ..auth import current_user, admin
from ..db import connect
from ..scheduling_models import CourseInput, SlotInput, ChangeInput, ReviewInput
from ..services import scheduling as store

router = APIRouter(prefix='/api/scheduling', tags=['志願排課'])


@router.get('/teachers')
def teachers(user=Depends(admin)):
    with connect() as db:
        return db.execute("SELECT user_id,username FROM users WHERE role='teacher' AND approval_status='approved' ORDER BY user_id").fetchall()


@router.get('/courses')
def courses(user=Depends(current_user)):
    store.require_staff(user)
    with connect() as db:
        if user['role'] == 'admin':
            return db.execute('SELECT * FROM courses ORDER BY course_id').fetchall()
        return db.execute('SELECT * FROM courses WHERE teacher_id=%s ORDER BY course_id',
                          (user['user_id'],)).fetchall()


@router.post('/courses', status_code=201)
def create_course(data: CourseInput, user=Depends(current_user)):
    store.require_staff(user)
    teacher_id = data.teacher_id or user['user_id']
    if user['role'] != 'admin' and teacher_id != user['user_id']:
        raise HTTPException(403, '老師不能指派其他老師')
    with connect() as db:
        store.scheduling_lock(db)
        store.teacher(db, teacher_id)
        return db.execute('INSERT INTO courses(title,teacher_id) VALUES (%s,%s) RETURNING *',
                          (data.title, teacher_id)).fetchone()


@router.get('/courses/{course_id}')
def course_detail(course_id: int, user=Depends(current_user)):
    with connect() as db:
        return store.get_course(db, course_id, user)


@router.put('/courses/{course_id}')
def update_course(course_id: int, data: CourseInput, user=Depends(current_user)):
    with connect() as db:
        store.scheduling_lock(db)
        old = store.get_course(db, course_id, user, active=True)
        teacher_id = data.teacher_id or old['teacher_id']
        if teacher_id != old['teacher_id'] and user['role'] != 'admin':
            raise HTTPException(403, '只有管理員可以重新指派老師')
        store.teacher(db, teacher_id)
        if teacher_id != old['teacher_id']:
            from ..services.availability import ensure_available, series_events
            all_rows = db.execute('SELECT * FROM schedule_series WHERE course_id=%s', (course_id,)).fetchall()
            for row in all_rows:
                store.require_upcoming(series_events(db,row))
            rows = [r for r in all_rows if r['active']]
            extra_rooms = db.execute('SELECT e.room_id FROM schedule_exceptions e JOIN schedule_series s USING(series_id) '
                                    'WHERE s.course_id=%s',(course_id,)).fetchall()
            store.lock_resources(db, [teacher_id, old['teacher_id']], [r['room_id'] for r in rows+extra_rooms])
            for row in rows:
                proposed = dict(row, teacher_id=teacher_id)
                ensure_available(db, series_events(db, proposed), exclude_series=row['series_id'], exclude_course=course_id)
            db.execute('UPDATE schedule_series SET teacher_id=%s,version=version+1 WHERE course_id=%s AND active', (teacher_id,course_id))
        return db.execute('UPDATE courses SET title=%s,teacher_id=%s WHERE course_id=%s RETURNING *',
                          (data.title, teacher_id, course_id)).fetchone()


@router.delete('/courses/{course_id}')
def delete_course(course_id: int, user=Depends(current_user)):
    with connect() as db:
        store.scheduling_lock(db)
        store.get_course(db, course_id, user)
        rows = db.execute('SELECT * FROM schedule_series WHERE course_id=%s', (course_id,)).fetchall()
        if rows:
            store.lock_resources(db,[r['teacher_id'] for r in rows],[r['room_id'] for r in rows])
            db.execute('UPDATE courses SET active=false WHERE course_id=%s', (course_id,))
            db.execute('UPDATE schedule_series SET active=false,version=version+1 WHERE course_id=%s', (course_id,))
            return {'course_id':course_id,'action':'deactivated'}
        db.execute('DELETE FROM courses WHERE course_id=%s', (course_id,))
        return {'course_id':course_id,'action':'deleted'}


@router.get('/courses/{course_id}/preferences')
def preferences(course_id: int, user=Depends(current_user)):
    with connect() as db:
        store.get_course(db,course_id,user)
        return db.execute('SELECT * FROM schedule_preferences WHERE course_id=%s ORDER BY preference_id', (course_id,)).fetchall()


@router.post('/courses/{course_id}/preferences', status_code=201)
def create_preference(course_id: int, data: SlotInput, user=Depends(current_user)):
    with connect() as db:
        store.scheduling_lock(db)
        store.get_course(db,course_id,user,active=True)
        store.room(db,data.room_id)
        return store.insert_slot(db,'schedule_preferences',course_id,data.model_dump())


@router.put('/courses/{course_id}/preferences/{preference_id}')
def update_preference(course_id: int, preference_id: int, data: SlotInput, user=Depends(current_user)):
    with connect() as db:
        store.scheduling_lock(db)
        store.get_course(db,course_id,user,active=True)
        store.room(db,data.room_id)
        row = db.execute('UPDATE schedule_preferences SET room_id=%s,start_date=%s,end_date=%s,weekday=%s,start_time=%s,end_time=%s '
                         'WHERE preference_id=%s AND course_id=%s RETURNING *',
                         (data.room_id,data.start_date,data.end_date,data.weekday,data.start_time,data.end_time,preference_id,course_id)).fetchone()
        if not row:
            raise HTTPException(404, '志願不存在')
        return row


@router.delete('/courses/{course_id}/preferences/{preference_id}')
def delete_preference(course_id: int, preference_id: int, user=Depends(current_user)):
    with connect() as db:
        store.scheduling_lock(db)
        store.get_course(db,course_id,user,active=True)
        row = db.execute('DELETE FROM schedule_preferences WHERE preference_id=%s AND course_id=%s RETURNING preference_id',
                         (preference_id,course_id)).fetchone()
        if not row:
            raise HTTPException(404,'志願不存在')
        return row


@router.get('/calendar')
def calendar(week_start: date, user=Depends(current_user)):
    store.require_staff(user)
    if week_start > date.max-timedelta(days=6):
        raise HTTPException(422,'週查詢超過日期範圍')
    from ..services.availability import calendar_events
    with connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        return {'week_start':week_start,'timezone':'Asia/Taipei',
                'events':calendar_events(db,week_start,week_start+timedelta(days=6)),
                'booking_integration':'not_connected'}


@router.get('/courses/{course_id}/series')
def course_series(course_id: int, user=Depends(current_user)):
    with connect() as db:
        store.get_course(db,course_id,user)
        return db.execute('SELECT * FROM schedule_series WHERE course_id=%s ORDER BY series_id', (course_id,)).fetchall()


@router.post('/courses/{course_id}/series',status_code=201)
def confirm_series(course_id: int, data: SlotInput, user=Depends(admin)):
    with connect() as db:
        store.scheduling_lock(db)
        return _confirm(db,course_id,data,user)


def _confirm(db,course_id,data,user):
    from ..services.availability import ensure_available
    from ..services.scheduling_time import occurrences
    course = store.get_course(db,course_id,user,active=True)
    store.lock_resources(db,[course['teacher_id']],[data.room_id])
    store.teacher(db,course['teacher_id'])
    store.room(db,data.room_id,formal=True)
    proposed = dict(data.model_dump(),course_id=course_id,series_id=0,teacher_id=course['teacher_id'])
    events=occurrences(proposed,[],data.start_date,data.end_date)
    store.require_upcoming(events)
    ensure_available(db,events)
    return store.insert_slot(db,'schedule_series',course_id,data.model_dump(),
                             dict(teacher_id=course['teacher_id'],created_by=user['user_id']))


@router.post('/courses/{course_id}/preferences/{preference_id}/confirm',status_code=201)
def confirm_preference(course_id: int, preference_id: int, user=Depends(admin)):
    with connect() as db:
        store.scheduling_lock(db)
        store.get_course(db,course_id,user,active=True)
        row=db.execute('SELECT * FROM schedule_preferences WHERE course_id=%s AND preference_id=%s FOR UPDATE',
                       (course_id,preference_id)).fetchone()
        if not row:
            raise HTTPException(404,'志願不存在，請重新讀取清單')
        values={key:row[key] for key in SlotInput.model_fields}
        return _confirm(db,course_id,SlotInput(**values),user)


@router.get('/conflicts')
def conflicts(week_start: date, source: Literal['formal','preferences']='formal', user=Depends(admin)):
    from itertools import combinations
    from ..services.availability import calendar_events, conflict
    from ..services.scheduling_time import occurrences
    if week_start > date.max-timedelta(days=6):
        raise HTTPException(422,'週查詢超過日期範圍')
    with connect() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        if source == 'formal':
            events = calendar_events(db,week_start,week_start+timedelta(days=6))
        else:
            rows = db.execute('SELECT p.*,c.teacher_id,c.title FROM schedule_preferences p '
                              'JOIN courses c USING(course_id) WHERE c.active').fetchall()
            events=[]
            for row in rows:
                events.extend(occurrences(dict(row,series_id=row['preference_id']),[],week_start,week_start+timedelta(days=6)))
        found = [item for a,b in combinations(events,2) if (item := conflict(a,b))]
        return {'conflicts':found,'source':source,'booking_integration':'not_connected',
                'note':'正式課表衝突；志願可重疊，不代表已占用'}


@router.post('/series/{series_id}/changes',status_code=201)
def request_change(series_id: int, data: ChangeInput, user=Depends(current_user)):
    import json
    from psycopg.types.json import Jsonb
    with connect() as db:
        store.scheduling_lock(db)
        row = store.get_series(db,series_id,user)
        if not row['start_date'] <= data.effective_date <= row['end_date'] or data.effective_date.weekday() != row['weekday']:
            raise HTTPException(422,'effective_date 必須是原週課表的上課日')
        if not row['start_date'] <= data.new_date <= row['end_date']:
            raise HTTPException(422,'新日期須在原課表起訖範圍內')
        if data.scope == 'future' and data.new_date < data.effective_date:
            raise HTTPException(422,'後續安排不能移至生效日之前')
        store.validate_change_timing(db,row,data.model_dump())
        store.room(db,data.room_id)
        snapshot = dict(row)
        snapshot['exceptions'] = db.execute('SELECT * FROM schedule_exceptions WHERE series_id=%s', (series_id,)).fetchall()
        values = data.model_dump()
        values.update(series_id=series_id,requested_by=user['user_id'],series_version=row['version'],
                      original=Jsonb(json.loads(json.dumps(snapshot,default=str))))
        from psycopg import sql
        return db.execute(sql.SQL('INSERT INTO schedule_change_requests ({}) VALUES ({}) RETURNING *').format(
            sql.SQL(',').join(map(sql.Identifier,values)),sql.SQL(',').join(sql.Placeholder() for _ in values)),
            tuple(values.values())).fetchone()


@router.get('/changes')
def changes(user=Depends(current_user)):
    store.require_staff(user)
    with connect() as db:
        if user['role'] == 'admin':
            return db.execute('SELECT * FROM schedule_change_requests ORDER BY change_id').fetchall()
        return db.execute('SELECT r.* FROM schedule_change_requests r JOIN schedule_series s USING(series_id) '
                          'JOIN courses c USING(course_id) WHERE c.teacher_id=%s ORDER BY change_id',
                          (user['user_id'],)).fetchall()


@router.post('/changes/{change_id}/review')
def review_change(change_id: int, data: ReviewInput, user=Depends(admin)):
    from ..services.availability import ensure_available, series_events
    with connect() as db:
        store.scheduling_lock(db)
        request = db.execute('SELECT * FROM schedule_change_requests WHERE change_id=%s FOR UPDATE', (change_id,)).fetchone()
        if not request:
            raise HTTPException(404,'調課申請不存在')
        if request['status'] != 'pending':
            raise HTTPException(409,'申請已處理')
        if data.status == 'approved':
            row = store.get_series(db,request['series_id'],user)
            if request['series_version'] != row['version']:
                raise HTTPException(409,'課表已變更，請重新提出申請；管理員可退回舊申請')
            exception_rows = db.execute('SELECT * FROM schedule_exceptions WHERE series_id=%s', (row['series_id'],)).fetchall()
            room_ids = [row['room_id'],request['room_id']] + [e['room_id'] for e in exception_rows]
            store.lock_resources(db,[row['teacher_id']],room_ids)
            store.validate_change_timing(db,row,request)
            store.teacher(db,row['teacher_id'])
            store.room(db,request['room_id'],formal=True)
            if request['scope'] == 'single':
                proposed_exception = dict(origin_date=request['effective_date'],date=request['new_date'],
                                          room_id=request['room_id'],start_time=request['start_time'],end_time=request['end_time'])
                remaining = [e for e in exception_rows if e['origin_date'] != request['effective_date']]
                proposed = series_events(db,row,exceptions=remaining+[proposed_exception])
                ensure_available(db,proposed,exclude_series=row['series_id'])
                restored = (request['new_date'] == request['effective_date']
                            and all(request[k] == row[k] for k in ('room_id','start_time','end_time')))
                if restored:
                    db.execute('DELETE FROM schedule_exceptions WHERE series_id=%s AND origin_date=%s',
                               (row['series_id'],request['effective_date']))
                else:
                    db.execute('INSERT INTO schedule_exceptions(series_id,origin_date,date,room_id,start_time,end_time) '
                               'VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(series_id,origin_date) DO UPDATE '
                               'SET date=excluded.date,room_id=excluded.room_id,start_time=excluded.start_time,end_time=excluded.end_time',
                               (row['series_id'],request['effective_date'],request['new_date'],request['room_id'],request['start_time'],request['end_time']))
                db.execute('UPDATE schedule_series SET version=version+1 WHERE series_id=%s', (row['series_id'],))
            else:
                cutoff = request['effective_date']
                if any(e['origin_date'] >= cutoff or e['date'] >= cutoff for e in exception_rows):
                    raise HTTPException(409,'後續安排含已核准單次調課，請先協調處理例外')
                new = dict(row,start_date=request['new_date'],weekday=request['new_weekday'],
                           room_id=request['room_id'],start_time=request['start_time'],end_time=request['end_time'])
                new_events = series_events(db,new,exceptions=[])
                old_events = [e for e in series_events(db,row) if e['origin_date'] < cutoff]
                ensure_available(db,old_events+new_events,exclude_series=row['series_id'])
                if cutoff <= row['start_date'] + timedelta(days=(row['weekday']-row['start_date'].weekday())%7):
                    db.execute('UPDATE schedule_series SET active=false,version=version+1 WHERE series_id=%s',(row['series_id'],))
                else:
                    db.execute('UPDATE schedule_series SET end_date=%s,version=version+1 WHERE series_id=%s',
                               (cutoff-timedelta(days=1),row['series_id']))
                fields = {key:new[key] for key in ('room_id','start_date','end_date','weekday','start_time','end_time')}
                store.insert_slot(db,'schedule_series',row['course_id'],fields,
                                  dict(teacher_id=row['teacher_id'],created_by=user['user_id']))
        return db.execute('UPDATE schedule_change_requests SET status=%s,reviewed_by=%s,reviewed_at=now(),review_note=%s '
                          'WHERE change_id=%s RETURNING *',(data.status,user['user_id'],data.note,change_id)).fetchone()
