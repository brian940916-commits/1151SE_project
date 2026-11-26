from datetime import date, time

from app.services.scheduling_time import occurrences, overlaps


def series(**changes):
    return dict(series_id=1, course_id=1, teacher_id=2, room_id=3,
                start_date=date(2027, 2, 1), end_date=date(2027, 2, 28),
                weekday=1, start_time=time(10), end_time=time(12), **changes)


def test_recurs_only_on_tuesdays_inside_term():
    rows = occurrences(series(), [], date(2027, 2, 1), date(2027, 2, 28))
    assert [r['date'].isoformat() for r in rows] == ['2027-02-02', '2027-02-09', '2027-02-16', '2027-02-23']


def test_cross_week_exception_removes_original_and_appears_in_target_week():
    exceptions = [dict(origin_date=date(2027, 2, 2), date=date(2027, 2, 10),
                       start_time=time(14), end_time=time(16), room_id=4)]
    assert occurrences(series(), exceptions, date(2027, 2, 1), date(2027, 2, 7)) == []
    rows = occurrences(series(), exceptions, date(2027, 2, 8), date(2027, 2, 14))
    assert [(r['date'].isoformat(), r['room_id']) for r in rows] == [('2027-02-09', 3), ('2027-02-10', 4)]


def test_adjacent_intervals_do_not_overlap():
    a = dict(date=date(2027, 2, 2), start_time=time(10), end_time=time(12))
    assert not overlaps(a, dict(a, start_time=time(12), end_time=time(13)))
    assert overlaps(a, dict(a, start_time=time(11), end_time=time(13)))
    assert not overlaps(a, dict(a, date=date(2027, 2, 3)))


def test_term_boundary_inclusive():
    value = series()
    value['start_date'] = value['end_date'] = date(2027, 2, 2)
    assert len(occurrences(value, [], date(2027, 2, 2), date(2027, 2, 2))) == 1
    assert occurrences(value, [], date(2027, 2, 3), date(2027, 2, 8)) == []


def test_last_supported_date_does_not_overflow():
    value = series()
    value.update(start_date=date(9999,12,31),end_date=date(9999,12,31),weekday=4)
    assert len(occurrences(value,[],date(9999,12,31),date(9999,12,31))) == 1
