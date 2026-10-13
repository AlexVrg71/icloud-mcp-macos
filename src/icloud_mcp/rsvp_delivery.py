"""iMIP reply for imported invitations that have no server-managed Schedule-Tag."""
import hashlib
import json
import os
from copy import deepcopy
from email.message import EmailMessage
from email.utils import make_msgid, formatdate
from pathlib import Path
import threading
import icalendar

_LOCK = threading.RLock()


def require_direct_reply(settings):
    from .cal import CalendarError
    if not settings.allow_send or settings.require_approval:
        raise CalendarError('This imported invitation needs an email RSVP. Enable direct mail with native client approval, or answer it in your calendar app. Nothing changed.')


def send_reply(settings, ev, own_attendees, organizer, calendar_id, previous_partstat):
    from .mail import MailService
    from .cal import CalendarError
    identity = '|'.join((calendar_id, str(ev['uid']), str(ev.get('recurrence-id', '')), organizer.lower(), settings.email_address.lower()))
    key = hashlib.sha256(identity.encode()).hexdigest()
    root = Path(settings.data_dir) / 'rsvp-delivery'
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    root.chmod(0o700)
    path = root / (key + '.json')
    partstat = str(own_attendees[0].params['PARTSTAT'])
    sequence = int(ev.get('sequence', 0))
    def save(record):
        tmp = path.with_suffix('.tmp')
        with tmp.open('wb') as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(json.dumps(record).encode())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        fd = os.open(root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    with _LOCK:
        previous = json.loads(path.read_text()) if path.exists() else {}
        if previous.get('state') in ('attempting', 'unknown'):
            return {'reply_delivery': 'unknown', 'reply_message_id': previous.get('message_id'),
                    'warning': 'A prior email RSVP has an uncertain delivery outcome. Do not resend automatically; check Sent and the organizer first.'}
        if previous.get('state') == 'sent' and previous.get('partstat') == partstat and previous.get('sequence') == sequence and previous_partstat == partstat:
            return {'reply_delivery': 'sent', 'reply_already_sent': True, 'reply_message_id': previous['message_id']}
        reply = icalendar.Calendar()
        reply.add('version', '2.0')
        reply.add('prodid', '-//iCloud MCP for macOS//Calendar reply//EN')
        reply.add('method', 'REPLY')
        component = deepcopy(ev)
        component.pop('attendee', None)
        for attendee in own_attendees:
            component.add('attendee', deepcopy(attendee))
        # Scheduling control parameters apply to CalDAV resources, not iTIP messages.
        copied_attendees = component['attendee'] if isinstance(component['attendee'], list) else [component['attendee']]
        for value in [component.get('organizer'), *copied_attendees]:
            if value is not None:
                for name in ('SCHEDULE-AGENT', 'SCHEDULE-FORCE-SEND', 'SCHEDULE-STATUS'):
                    value.params.pop(name, None)
        component.subcomponents = []  # Do not transmit alarms in a reply.
        reply.add_component(component)
        reply.add_missing_timezones()
        mail = MailService(settings)
        msg = EmailMessage()
        msg['From'] = settings.email_address
        msg['To'] = organizer
        msg['Subject'] = f'{partstat.title()}: {str(ev.get("summary") or "Calendar invitation")}'
        msg['Date'] = formatdate(usegmt=True)
        msg['Message-ID'] = make_msgid(domain=settings.email_address.split('@')[-1])
        msg.set_content(f'Calendar response: {partstat.lower()}.')
        msg.add_alternative(reply.to_ical().decode(), subtype='calendar', params={'method': 'REPLY'})
        mail._check_recipients(msg)  # Same recipient cap and allowlist as ordinary mail.
        record = {'state': 'attempting', 'partstat': partstat, 'sequence': sequence, 'message_id': str(msg['Message-ID'])}
        with mail.imap() as connection:
            save(record)  # Durable uncertainty marker BEFORE any SMTP write.
            try:
                result = mail._deliver(connection, msg, draft=False)
                if result.get('status') != 'sent' or result.get('refused'):
                    raise CalendarError('Email RSVP was not accepted for delivery.')
            except Exception as exc:
                record['state'] = 'unknown'
                try:
                    save(record)
                except OSError:
                    pass  # The already durable 'attempting' marker still blocks retries.
                raise CalendarError(f'The calendar response was saved, but email delivery is uncertain. Do not retry automatically; check Sent for {record["message_id"]}.') from exc
            record['state'] = 'sent'
            try:
                save(record)
            except OSError:
                return {'reply_delivery': 'sent', 'reply_message_id': record['message_id'],
                        'warning': 'Reply sent, but its final local receipt could not be saved. Do not repeat it.'}
        return {'reply_delivery': 'sent', 'reply_message_id': record['message_id'],
                **({'warning': result['warning']} if result.get('warning') else {})}
