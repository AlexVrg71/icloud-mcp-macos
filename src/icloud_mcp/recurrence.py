"""Truncate a series in one conditional CalDAV write, preserving earlier exceptions."""
from datetime import datetime, timedelta, timezone

def truncate_future(parsed, master, rid):
    until = rid - (timedelta(seconds=1) if isinstance(rid,datetime) else timedelta(days=1))
    if isinstance(until,datetime) and until.tzinfo: until=until.astimezone(timezone.utc)
    rule=master.get('rrule')
    if rule is not None:
        rule.pop('COUNT',None)
        rule['UNTIL']=[until]
    for key in ('rdate','exdate'):
        raw=master.pop(key,None)
        for prop in raw if isinstance(raw,list) else ([raw] if raw is not None else []):
            kept=[entry.dt for entry in prop.dts if entry.dt < rid]
            if kept: master.add(key,kept)
    parsed.subcomponents=[c for c in parsed.subcomponents if c.name!='VEVENT' or c.get('recurrence-id') is None or c['recurrence-id'].dt < rid]


def preserve_range_after(parsed, boundary):
    """Move a range's continuation to the next non-overridden original recurrence."""
    import icalendar
    from dateutil.rrule import rrulestr, rruleset
    from .cal import CalendarError, _risky
    master = next(e for e in parsed.walk('VEVENT') if e.get('recurrence-id') is None)
    rid = boundary['recurrence-id'].dt
    start = master['dtstart'].dt
    timed = isinstance(start, datetime)
    as_dt = (lambda x: x) if timed else (lambda x: datetime.combine(x, datetime.min.time()))
    series = rruleset()
    series.rdate(as_dt(start))
    rule = master.get('rrule')
    if rule is not None:
        if _risky(rule, start, rid):
            raise CalendarError('The recurrence is too costly to safely isolate this date. No changes made.')
        text = rule.to_ical().decode()
        if timed and start.tzinfo is None:
            import re
            text = re.sub(r'UNTIL=(\d{8}T\d{6})Z', r'UNTIL=\1', text)
        series.rrule(rrulestr(text, dtstart=as_dt(start)))
    for key, add in [('rdate', series.rdate), ('exdate', series.exdate)]:
        raw = master.get(key)
        for prop in raw if isinstance(raw, list) else ([raw] if raw is not None else []):
            for entry in prop.dts:
                add(as_dt(entry.dt))
    overrides = {e['recurrence-id'].dt: e for e in parsed.walk('VEVENT') if e.get('recurrence-id') is not None}
    for candidate in series.xafter(as_dt(rid), count=len(overrides) + 1):
        candidate = candidate if timed else candidate.date()
        existing = overrides.get(candidate)
        if existing is not None:
            if existing['recurrence-id'].params.get('RANGE') == 'THISANDFUTURE':
                break  # A later range already controls everything from here.
            continue
        continuation = icalendar.Event.from_ical(boundary.to_ical())
        shift = candidate - rid
        continuation['recurrence-id'].dt = candidate
        continuation['dtstart'].dt += shift
        if continuation.get('dtend') is not None:
            continuation['dtend'].dt += shift
        parsed.add_component(continuation)
        break
    boundary['recurrence-id'].params.pop('RANGE', None)


def make_continuation(parsed, edited, rid, original_start, new_uid):
    """Build a new master and preserve dated future exceptions under the new UID."""
    import icalendar
    from copy import deepcopy
    old_master = next(e for e in parsed.walk('VEVENT') if e.get('recurrence-id') is None)
    future = deepcopy(parsed)
    future.subcomponents = [c for c in future.subcomponents if c.name != 'VEVENT']
    master = deepcopy(edited)
    master.pop('recurrence-id', None)
    master.pop('rdate', None)
    master.pop('exdate', None)
    master['uid'] = new_uid
    master.add('related-to', str(old_master['uid']), parameters={'RELTYPE': 'SIBLING'})
    future.add_component(master)
    if master.get('rrule') is None:
        return future
    id_shift = master['dtstart'].dt - rid
    actual_shift = master['dtstart'].dt - original_start
    for key in ('rdate', 'exdate'):
        raw = old_master.get(key)
        for prop in raw if isinstance(raw, list) else ([raw] if raw is not None else []):
            kept = [entry.dt + id_shift for entry in prop.dts if entry.dt > rid]
            if kept:
                master.add(key, kept)
    for event in parsed.walk('VEVENT'):
        rec = event.get('recurrence-id')
        if rec is None or rec.dt <= rid:
            continue
        exception = deepcopy(event)
        exception['uid'] = new_uid
        exception['recurrence-id'].dt += id_shift
        exception['dtstart'].dt += actual_shift
        if exception.get('dtend') is not None:
            exception['dtend'].dt += actual_shift
        # Keep explicit future exceptions even when the new rule would not generate their dates.
        master.add('rdate', exception['recurrence-id'].dt)
        future.add_component(exception)
    future.add_missing_timezones()
    return future
