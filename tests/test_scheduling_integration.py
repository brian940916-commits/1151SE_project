from concurrent.futures import ThreadPoolExecutor

from conftest import headers, course, slot

BASE = '/api/scheduling'


def formal(api, cid, auth, **changes):
    return api.post(f'{BASE}/courses/{cid}/series',json=slot(**changes),headers=auth)


def change(api, sid, auth, **changes):
    value = dict(scope='single',effective_date='2027-02-02',new_date='2027-02-10',new_weekday=2,
                 room_id=2,start_time='14:00',end_time='16:00')
    value.update(changes)
    return api.post(f'{BASE}/series/{sid}/changes',json=value,headers=auth)


def review(api, change_id, auth, status='approved'):
    return api.post(f'{BASE}/changes/{change_id}/review',json={'status':status,'note':'checked'},headers=auth)


def test_formal_permissions_and_room_teacher_conflicts(api):
    t1,t2,admin = headers(api),headers(api,'teacher2'),headers(api,'admin1')
    a,b,c = course(api,t1),course(api,t2),course(api,t1)
    assert formal(api,a,t1).status_code == 403
    assert formal(api,a,admin,room_id=3).status_code == 409
    assert formal(api,a,admin).status_code == 201
    assert formal(api,b,admin).status_code == 409  # room
    assert formal(api,c,admin,room_id=2).status_code == 409  # teacher
    assert formal(api,b,admin,room_id=2).status_code == 201
    assert formal(api,c,admin,start_time='12:00',end_time='13:00').status_code == 201
    r = api.get(f'{BASE}/calendar?week_start=2027-02-01',headers=t1)
    assert len(r.json()['events']) == 3
    assert api.get(f'{BASE}/conflicts?week_start=2027-02-01',headers=admin).json()['conflicts'] == []
    assert api.get(f'{BASE}/conflicts?week_start=2027-02-01',headers=t1).status_code == 403


def test_single_change_pending_then_approved_and_no_double_review(api):
    t1,admin = headers(api),headers(api,'admin1')
    cid=course(api,t1)
    sid=formal(api,cid,admin).json()['series_id']
    r=change(api,sid,t1)
    assert r.status_code == 201,r.text
    rid=r.json()['change_id']
    week=lambda day: api.get(f'{BASE}/calendar?week_start={day}',headers=t1).json()['events']
    assert [x['date'] for x in week('2027-02-01')] == ['2027-02-02']
    assert review(api,rid,t1).status_code == 403
    assert review(api,rid,admin).status_code == 200
    assert week('2027-02-01') == []
    assert [x['date'] for x in week('2027-02-08')] == ['2027-02-09','2027-02-10']
    assert review(api,rid,admin).status_code == 409
    future=change(api,sid,t1,scope='future',effective_date='2027-02-02',new_date='2027-02-03')
    assert review(api,future.json()['change_id'],admin).status_code == 409
    assert len(week('2027-02-08')) == 2


def test_future_change_splits_series_and_stales_pending_request(api):
    t1,admin = headers(api),headers(api,'admin1')
    sid=formal(api,course(api,t1),admin).json()['series_id']
    stale=change(api,sid,t1,effective_date='2027-02-16',new_date='2027-02-17')
    future=change(api,sid,t1,scope='future',effective_date='2027-02-09',new_date='2027-02-10')
    assert review(api,future.json()['change_id'],admin).status_code == 200
    assert review(api,stale.json()['change_id'],admin).status_code == 409
    events=api.get(f'{BASE}/calendar?week_start=2027-02-08',headers=t1).json()['events']
    assert [x['date'] for x in events] == ['2027-02-10']
    events=api.get(f'{BASE}/calendar?week_start=2027-02-01',headers=t1).json()['events']
    assert [x['date'] for x in events] == ['2027-02-02']


def test_conflicting_change_rolls_back_and_keeps_pending(api):
    t1,t2,admin=headers(api),headers(api,'teacher2'),headers(api,'admin1')
    sid=formal(api,course(api,t1),admin).json()['series_id']
    assert formal(api,course(api,t2),admin,room_id=2,weekday=2,start_time='14:00',end_time='16:00').status_code == 201
    rid=change(api,sid,t1).json()['change_id']
    assert review(api,rid,admin).status_code == 409
    rows=api.get(f'{BASE}/changes',headers=t1).json()
    assert rows[0]['status'] == 'pending'
    events=api.get(f'{BASE}/calendar?week_start=2027-02-01',headers=t1).json()['events']
    assert any(x['date']=='2027-02-02' and x['series_id']==sid for x in events)
    assert review(api,rid,admin,'rejected').status_code == 200


def test_reassignment_checks_teacher_conflicts_and_inactive_course_history(api):
    t1,t2,admin=headers(api),headers(api,'teacher2'),headers(api,'admin1')
    a,b=course(api,t1),course(api,t2)
    formal(api,a,admin)
    formal(api,b,admin,room_id=2)
    assert api.put(f'{BASE}/courses/{b}',json={'title':'x','teacher_id':1},headers=admin).status_code == 409
    assert api.delete(f'{BASE}/courses/{a}',headers=t1).json()['action']=='deactivated'
    assert api.get(f'{BASE}/courses/{a}',headers=admin).json()['active'] is False
    assert api.put(f'{BASE}/courses/{b}',json={'title':'x','teacher_id':1},headers=admin).status_code == 200


def test_parallel_confirmation_cannot_double_book(api):
    t1,t2,admin=headers(api),headers(api,'teacher2'),headers(api,'admin1')
    a,b=course(api,t1),course(api,t2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(lambda cid:formal(api,cid,admin).status_code,[a,b]))
    assert sorted(codes)==[201,409]


def test_same_teacher_parallel_different_rooms_cannot_double_book(api):
    t1,admin=headers(api),headers(api,'admin1')
    a,b=course(api,t1),course(api,t1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(lambda args:formal(api,args[0],admin,room_id=args[1]).status_code,[(a,1),(b,2)]))
    assert sorted(codes)==[201,409]


def test_request_note_is_preserved_and_inactive_request_can_be_rejected(api):
    t1,admin=headers(api),headers(api,'admin1')
    cid=course(api,t1)
    sid=formal(api,cid,admin).json()['series_id']
    rid=change(api,sid,t1,note='conference').json()['change_id']
    row=review(api,rid,admin).json()
    assert row['note']=='conference'
    assert row['review_note']=='checked'
    rid=change(api,sid,t1,effective_date='2027-02-16',new_date='2027-02-17').json()['change_id']
    api.delete(f'{BASE}/courses/{cid}',headers=admin)
    assert review(api,rid,admin,'rejected').status_code==200


def test_admin_can_find_conflicting_wishes_before_confirmation(api):
    t1,t2,admin=headers(api),headers(api,'teacher2'),headers(api,'admin1')
    a,b=course(api,t1),course(api,t2)
    for cid,auth in [(a,t1),(b,t2)]:
        api.post(f'{BASE}/courses/{cid}/preferences',json=slot(),headers=auth)
    r=api.get(f'{BASE}/conflicts?week_start=2027-02-01&source=preferences',headers=admin)
    assert r.status_code==200,r.text
    assert len(r.json()['conflicts'])==1
    assert r.json()['conflicts'][0]['kinds']==['room']


def test_calendar_extreme_date_returns_validation_error(api):
    assert api.get(f'{BASE}/calendar?week_start=9999-12-31',headers=headers(api)).status_code==422


def test_restoring_single_exception_unblocks_future_change(api):
    t1,admin=headers(api),headers(api,'admin1')
    sid=formal(api,course(api,t1),admin).json()['series_id']
    rid=change(api,sid,t1).json()['change_id']
    assert review(api,rid,admin).status_code==200
    restore=change(api,sid,t1,new_date='2027-02-02',new_weekday=1,room_id=1,start_time='10:00',end_time='12:00')
    assert review(api,restore.json()['change_id'],admin).status_code==200
    future=change(api,sid,t1,scope='future',effective_date='2027-02-02',new_date='2027-02-03')
    assert review(api,future.json()['change_id'],admin).status_code==200
    events=api.get(f'{BASE}/calendar?week_start=2027-02-01',headers=t1).json()['events']
    assert [e['date'] for e in events]==['2027-02-03']


def test_elapsed_classes_cannot_be_reassigned_or_backdated(api,monkeypatch):
    from datetime import datetime
    from app.services import scheduling as store
    t1,admin=headers(api),headers(api,'admin1')
    cid=course(api,t1)
    sid=formal(api,cid,admin).json()['series_id']
    monkeypatch.setattr(store,'local_now',lambda:datetime(2027,2,3),raising=False)
    assert api.put(f'{BASE}/courses/{cid}',json={'title':'x','teacher_id':2},headers=admin).status_code==409
    assert change(api,sid,t1).status_code==409
    assert change(api,sid,t1,effective_date='2027-02-09',new_date='2027-02-02',new_weekday=1).status_code==409
    assert formal(api,course(api,t1),admin,room_id=2).status_code==409


def test_delayed_approval_cannot_change_elapsed_occurrence(api,monkeypatch):
    from datetime import datetime
    from app.services import scheduling as store
    t1,admin=headers(api),headers(api,'admin1')
    sid=formal(api,course(api,t1),admin).json()['series_id']
    rid=change(api,sid,t1).json()['change_id']
    monkeypatch.setattr(store,'local_now',lambda:datetime(2027,2,3),raising=False)
    assert review(api,rid,admin).status_code==409
    assert review(api,rid,admin,'rejected').status_code==200


def test_confirmation_uses_current_preference_by_id(api):
    t1,admin=headers(api),headers(api,'admin1')
    cid=course(api,t1)
    path=f'{BASE}/courses/{cid}/preferences'
    pid=api.post(path,json=slot(),headers=t1).json()['preference_id']
    api.put(f'{path}/{pid}',json=slot(room_id=2,start_time='14:00',end_time='16:00'),headers=t1)
    assert api.post(f'{path}/{pid}/confirm',headers=t1).status_code==403
    r=api.post(f'{path}/{pid}/confirm',headers=admin)
    assert r.status_code==201,r.text
    assert r.json()['room_id']==2 and r.json()['start_time']=='14:00:00'
    other=course(api,t1)
    assert api.post(f'{BASE}/courses/{other}/preferences/{pid}/confirm',headers=admin).status_code==404
    api.delete(f'{path}/{pid}',headers=t1)
    assert api.post(f'{path}/{pid}/confirm',headers=admin).status_code==404


def test_calendar_reads_one_committed_snapshot(api,monkeypatch):
    import os
    import psycopg
    from psycopg.rows import dict_row
    from app.routers import scheduling as router
    t1,admin=headers(api),headers(api,'admin1')
    sid=formal(api,course(api,t1),admin).json()['series_id']
    url=os.environ['SCHEDULING_TEST_DATABASE_URL']

    class ConcurrentConnection(psycopg.Connection):
        def execute(self,query,*args,**kwargs):
            result=super().execute(query,*args,**kwargs)
            if isinstance(query,str) and 'SELECT s.*,c.title' in query:
                # Commit a complete new version between the reader's series
                # query and exception query. A snapshot must see all or none.
                with psycopg.connect(url) as writer:
                    writer.execute('UPDATE schedule_series SET start_time=\'14:00\',end_time=\'16:00\',version=version+1 WHERE series_id=%s',(sid,))
                    writer.execute('INSERT INTO schedule_exceptions(series_id,origin_date,date,room_id,start_time,end_time) '
                                   "VALUES (%s,'2027-02-02','2027-02-03',2,'16:00','18:00')",(sid,))
            return result

    monkeypatch.setattr(router,'connect',lambda:ConcurrentConnection.connect(url,row_factory=dict_row))
    events=api.get(f'{BASE}/calendar?week_start=2027-02-01',headers=t1).json()['events']
    assert [(e['date'],e['start_time']) for e in events]==[('2027-02-02','10:00:00')]
