"""Formal scheduling occupancy. Bookings must integrate this service explicitly.

Callers writing occupancy must lock resources with scheduling.lock_resources in
the SAME transaction, before reading/checking/writing. No booking table exists
in the supplied project, so this module does not claim to check bookings.
"""
from datetime import date
from itertools import combinations

from fastapi import HTTPException

from .scheduling_time import occurrences, overlaps


def series_events(db, series, start_date=date.min, end_date=date.max, exceptions=None):
    if exceptions is None:
        exceptions = db.execute('SELECT * FROM schedule_exceptions WHERE series_id=%s',
                                (series['series_id'],)).fetchall()
    return occurrences(series, exceptions, start_date, end_date)


def calendar_events(db, start_date, end_date, exclude_series=None, exclude_course=None):
    # Also fetch moved-in exceptions whose origin series is outside this week.
    rows = db.execute('SELECT s.*,c.title FROM schedule_series s JOIN courses c USING(course_id) '
                      'WHERE s.active AND c.active ORDER BY series_id').fetchall()
    exceptions = db.execute('SELECT * FROM schedule_exceptions').fetchall()
    grouped = {}
    for row in exceptions:
        grouped.setdefault(row['series_id'], []).append(row)
    result = []
    for row in rows:
        if row['series_id'] == exclude_series or row['course_id'] == exclude_course:
            continue
        result.extend(series_events(db,row,start_date,end_date,grouped.get(row['series_id'],[])))
    return sorted(result,key=lambda r:(r['date'],r['start_time'],r['series_id']))


def conflict(a, b):
    kinds = []
    if overlaps(a,b):
        if a['room_id'] == b['room_id']:
            kinds.append('room')
        if a['teacher_id'] == b['teacher_id']:
            kinds.append('teacher')
    return {'kinds':kinds,'first':a,'second':b} if kinds else None


def ensure_available(db, proposed, exclude_series=None, exclude_course=None):
    if not proposed:
        raise HTTPException(422,'週期內沒有上課日')
    existing = calendar_events(db,min(r['date'] for r in proposed),max(r['date'] for r in proposed),
                               exclude_series,exclude_course)
    for a,b in combinations(proposed,2):
        if conflict(a,b):
            raise HTTPException(409,'調課造成同一課程的時段重疊')
    for a in proposed:
        for b in existing:
            if conflict(a,b):
                raise HTTPException(409,{'message':'正式課表時段衝突','date':str(a['date']),
                                         'series_id':b['series_id'],'kinds':conflict(a,b)['kinds']})
