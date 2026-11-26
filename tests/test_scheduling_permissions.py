from conftest import headers, course, slot


def test_roles_and_course_ownership(api):
    path = '/api/scheduling/courses'
    assert api.get(path).status_code == 401
    assert api.post(path, json={'title':'x'}, headers=headers(api,'student1')).status_code == 403
    t1, t2, admin = headers(api), headers(api,'teacher2'), headers(api,'admin1')
    cid = course(api, t1)
    assert api.get(f'{path}/{cid}', headers=t2).status_code == 403
    assert api.put(f'{path}/{cid}', json={'title':'偷改'}, headers=t2).status_code == 403
    assert api.delete(f'{path}/{cid}', headers=t2).status_code == 403
    assert api.get(path, headers=t2).json() == []
    assert api.put(f'{path}/{cid}', json={'title':'新課名','teacher_id':2}, headers=t1).status_code == 403
    assert api.put(f'{path}/{cid}', json={'title':'新課名','teacher_id':2}, headers=admin).status_code == 200
    assert api.get(f'{path}/{cid}', headers=t2).json()['title'] == '新課名'
    assert api.put(f'{path}/{cid}', json={'title':'x','teacher_id':4}, headers=admin).status_code == 422


def test_preferences_do_not_reserve_space(api):
    t1, t2 = headers(api), headers(api,'teacher2')
    a, b = course(api,t1), course(api,t2)
    for cid, auth in [(a,t1),(b,t2)]:
        r = api.post(f'/api/scheduling/courses/{cid}/preferences', json=slot(), headers=auth)
        assert r.status_code == 201, r.text
    assert api.get('/api/scheduling/calendar?week_start=2027-02-01',headers=t1).json()['events'] == []
    assert api.get(f'/api/scheduling/courses/{a}/preferences',headers=t2).status_code == 403


def test_invalid_period_is_rejected(api):
    auth = headers(api)
    cid = course(api,auth)
    path = f'/api/scheduling/courses/{cid}/preferences'
    for data in [slot(end_time='09:00'), slot(end_date='2027-01-01'), slot(weekday=7),
                 slot(start_time='10:00:00+08:00'), slot(end_date='2030-01-01')]:
        assert api.post(path,json=data,headers=auth).status_code == 422


def test_cookie_auth_and_header_precedence(api):
    auth = headers(api)
    api.cookies.set('access_token',auth['Authorization'][7:])
    assert api.get('/api/scheduling/courses').status_code == 200
    assert api.get('/api/scheduling/courses',headers={'Authorization':'Bearer wrong'}).status_code == 401
    assert api.post('/api/auth/logout').status_code == 204
    assert api.get('/api/auth/me',headers=auth).status_code == 401


def test_preference_edit_delete_and_teacher_choices(api):
    t1,t2,admin=headers(api),headers(api,'teacher2'),headers(api,'admin1')
    teachers=api.get('/api/scheduling/teachers',headers=admin)
    assert teachers.status_code==200
    assert [x['username'] for x in teachers.json()]==['teacher1','teacher2']
    assert api.get('/api/scheduling/teachers',headers=t1).status_code==403
    cid=course(api,t1)
    path=f'/api/scheduling/courses/{cid}/preferences'
    pid=api.post(path,json=slot(),headers=t1).json()['preference_id']
    assert api.put(f'{path}/{pid}',json=slot(room_id=2),headers=t2).status_code==403
    assert api.put(f'{path}/{pid}',json=slot(room_id=2),headers=t1).json()['room_id']==2
    assert api.delete(f'{path}/{pid}',headers=t1).status_code==200
    assert api.get(path,headers=t1).json()==[]
    assert api.delete(f'{path}/{pid}',headers=t1).status_code==404


def test_registration_review_login_and_existing_room_api(api):
    admin=headers(api,'admin1')
    data=dict(username='newteacher',password='password123',role='teacher')
    row=api.post('/api/auth/register',json=data)
    assert row.status_code==201
    assert row.json()['approval_status']=='pending'
    login=dict(username='newteacher',password='password123')
    assert api.post('/api/auth/login',json=login).status_code==403
    uid=row.json()['user_id']
    assert api.post(f'/api/admin/users/{uid}/review',json={'status':'approved'},headers=admin).status_code==200
    result=api.post('/api/auth/login',json=login)
    assert result.status_code==200
    auth={'Authorization':'Bearer '+result.json()['access_token']}
    assert api.get('/api/auth/me',headers=auth).json()['user_id']==uid
    assert course(api,auth)>0
    assert len(api.get('/api/rooms').json())==34


def test_student_cannot_probe_series_existence(api):
    student=headers(api,'student1')
    data=dict(scope='single',effective_date='2027-02-02',new_date='2027-02-03',new_weekday=2,
              room_id=1,start_time='10:00',end_time='12:00')
    assert api.post('/api/scheduling/series/999/changes',json=data,headers=student).status_code==403


def test_invalid_weekday_near_max_date_is_validation_error(api):
    auth=headers(api)
    cid=course(api,auth)
    response=api.post(f'/api/scheduling/courses/{cid}/preferences',headers=auth,
                      json=slot(start_date='9999-12-31',end_date='9999-12-31',weekday=0))
    assert response.status_code==422

