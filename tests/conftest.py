"""Integration tests require a DISPOSABLE database, name ending in _test.

Only that database's public schema is reset, once per test. Never use a real DB.
"""
import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def api(monkeypatch):
    url = os.environ.get('SCHEDULING_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set SCHEDULING_TEST_DATABASE_URL to a disposable *_test database')
    with psycopg.connect(url, autocommit=True) as db:
        name = db.execute('select current_database()').fetchone()[0]
        if not name.endswith('_test'):
            pytest.fail('Refusing to reset a database whose name does not end in _test')
        db.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
        for path in sorted((ROOT / 'database/migrations').glob('*.sql')):
            db.execute(path.read_text(encoding='utf-8'))
            db.execute(path.read_text(encoding='utf-8'))
        db.execute((ROOT / 'database/seed.sql').read_text(encoding='utf-8'))
    monkeypatch.setenv('DATABASE_URL', url)
    from app.main import app
    from app.security import hash_password
    from app.db import connect
    from app.services import scheduling
    from datetime import datetime
    monkeypatch.setattr(scheduling,'local_now',lambda:datetime(2027,1,1))
    with connect() as db:
        for name, role in [('teacher1','teacher'), ('teacher2','teacher'), ('admin1','admin'), ('student1','student')]:
            db.execute('INSERT INTO users(username,password_hash,role,approval_status) VALUES (%s,%s,%s,\'approved\')',
                       (name, hash_password('password123'), role))
        db.execute('UPDATE rooms SET is_schedulable=true WHERE room_id IN (1,2)')
    with TestClient(app) as client:
        yield client


def headers(api, name='teacher1'):
    r = api.post('/api/auth/login', json=dict(username=name, password='password123'))
    assert r.status_code == 200, r.text
    return {'Authorization': 'Bearer ' + r.json()['access_token']}


def course(api, auth, title='軟體工程', teacher_id=None):
    data = {'title': title}
    if teacher_id:
        data['teacher_id'] = teacher_id
    r = api.post('/api/scheduling/courses', json=data, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()['course_id']


def slot(**changes):
    value = dict(room_id=1, start_date='2027-02-01', end_date='2027-06-30',
                 weekday=1, start_time='10:00:00', end_time='12:00:00')
    value.update(changes)
    return value
