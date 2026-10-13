"""Two-resource recurrence splits with conditional writes and a durable recovery record."""
import json
import os
import uuid
from pathlib import Path
from urllib.parse import quote


def commit_split(service, cal, obj, past, future, uid, new_uid):
    from .cal import CalendarError
    if not getattr(obj, 'etag', None):
        raise CalendarError('Cannot safely split this series without its ETag. Read it again; nothing changed.')
    folder = Path(service.s.data_dir) / 'calendar-recovery' / uuid.uuid4().hex
    folder.mkdir(parents=True, mode=0o700)
    folder.parent.chmod(0o700)
    def write(name, data):
        tmp = folder / (name + '.tmp')
        with tmp.open('wb') as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, folder / name)
        fd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    record = {'original_uid': uid, 'continuation_uid': new_uid, 'state': 'prepared'}
    def state(value):
        record['state'] = value
        write('manifest.json', json.dumps(record).encode())
    original_etag = obj.etag
    write('original.ics', obj.data.encode() if isinstance(obj.data, str) else obj.data)
    write('past.ics', past.to_ical())
    write('continuation.ics', future.to_ical())
    state('prepared')
    url = str(cal.url).rstrip('/') + '/' + quote(new_uid, safe='') + '.ics'
    service._tl.mutated = True  # A timeout must never trigger an automatic retry.
    try:
        response = obj.client.request(url, 'PUT', future.to_ical().decode(),
                                      {'Content-Type': 'text/calendar; charset=utf-8', 'If-None-Match': '*'})
    except Exception as exc:
        state('creation_outcome_unknown')
        raise CalendarError(f'Series split outcome needs review; do not repeat the call. Recovery {folder.name}; original {uid}; continuation {new_uid}.') from exc
    if int(response.status) >= 500:
        state('creation_outcome_unknown')
        raise CalendarError(f'Series split outcome needs review after HTTP {response.status}; do not repeat the call. Recovery {folder.name}; original {uid}; continuation {new_uid}.')
    if not 200 <= int(response.status) < 300:
        state('creation_refused')
        raise CalendarError(f'Continuation creation was refused (HTTP {response.status}); original series is unchanged.')
    new_etag = response.headers.get('ETag') or response.headers.get('etag')
    try:
        state('continuation_created')
        if not new_etag:
            raise CalendarError('The server did not return an ETag for the new continuation.')
        service._save(obj, past, uid)
    except Exception as exc:
        # Only remove our new object when a fresh read proves the original is unchanged.
        rolled_back = False
        try:
            original_now = cal.event_by_url(str(obj.url))
            if original_now.etag == original_etag and new_etag:
                result = obj.client.request(url, 'DELETE', '', {'If-Match': new_etag})
                rolled_back = 200 <= int(result.status) < 300 or int(result.status) == 404
        except Exception:
            pass
        state('rolled_back' if rolled_back else 'needs_review')
        if rolled_back:
            raise CalendarError('The split was not completed; the continuation was removed and the original is unchanged. Read the series again before retrying.') from exc
        raise CalendarError(f'Series split outcome needs review; do not repeat the call. Recovery {folder.name}; original {uid}; continuation {new_uid}.') from exc
    service._uid_cache.pop(uid, None)
    try:
        state('committed')
    except OSError:
        return {'recovery_id': folder.name, 'warning': 'Split completed, but the final journal status could not be saved. Do not repeat it.'}
    return {'recovery_id': folder.name}
