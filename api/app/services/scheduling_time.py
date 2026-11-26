"""Local (Asia/Taipei) recurring dates; intervals are [start, end)."""
from datetime import timedelta


def occurrences(series, exceptions, start_date, end_date):
    replacements = {e['origin_date']: e for e in exceptions}
    result = []
    first = series['start_date']
    first += timedelta(days=(series['weekday'] - first.weekday()) % 7)
    day = first
    while day <= series['end_date']:
        value = dict(series, origin_date=day, date=day)
        if day in replacements:
            value.update(replacements[day])
        if start_date <= value['date'] <= end_date:
            result.append(value)
        if (series['end_date'] - day).days < 7:
            break
        day += timedelta(days=7)
    return sorted(result, key=lambda r: (r['date'], r['start_time'], r['series_id']))


def overlaps(a, b):
    return (a['date'] == b['date'] and a['start_time'] < b['end_time']
            and b['start_time'] < a['end_time'])
