import contextlib, hashlib, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock
import httpx
os.environ.update(ICLOUD_USERNAME='test@example.invalid',ICLOUD_APP_PASSWORD='synthetic',ICLOUD_KEYCHAIN='false',READ_ONLY='false',WARMUP_ON_START='false')
from icloud_mcp.config import Settings
from icloud_mcp.contacts import ContactsService, ContactsError
from icloud_mcp.contact_backup import save_snapshot
from dataclasses import replace
CARD='BEGIN:VCARD\r\nVERSION:3.0\r\nUID:test\r\nFN:Synthetic\r\nEND:VCARD\r\n'
XML='<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav"><d:response><d:href>/a.vcf</d:href><d:propstat><d:prop><d:getetag>"v1"</d:getetag><c:address-data>'+CARD+'</c:address-data></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response></d:multistatus>'
class BackupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.s=replace(Settings.from_env(),data_dir=self.tmp.name)
 def test_snapshot_bytes_permissions_and_manifest(self):
  name=save_snapshot(self.tmp.name,[{'url':'https://contacts.icloud.com/book','cards':[{'raw':CARD,'href':'/a','etag':'v1'}]}],'PUT')
  root=Path(self.tmp.name)/'contact-backups'/name
  m=json.loads((root/'manifest.json').read_text());self.assertEqual(m['cards'],1)
  self.assertEqual((root/'book-1.vcf').read_bytes(),CARD.encode())
  self.assertEqual(m['books'][0]['sha256'],hashlib.sha256(CARD.encode()).hexdigest())
  self.assertEqual(root.stat().st_mode&0o777,0o700)
  self.assertEqual((root/'book-1.vcf').stat().st_mode&0o777,0o600)
 def service(self,xml=XML):
  svc=ContactsService(self.s);svc._discover=Mock(return_value=['https://contacts.icloud.com/book/'])
  svc._dav=Mock(return_value=httpx.Response(207,text=xml))
  client=Mock();client.request.return_value=httpx.Response(204)
  return svc,client
 def test_backup_precedes_put_and_delete(self):
  for method in ('PUT','DELETE'):
   svc,c=self.service()
   def request(*a,**kw):
    self.assertTrue((Path(self.tmp.name)/'contact-backups'/svc.last_backup/'manifest.json').exists())
    self.assertEqual(kw['headers']['If-Match'],'v1');return httpx.Response(204)
   c.request.side_effect=request
   svc._mutate(c,method,'https://contacts.icloud.com/a.vcf',etag='v1');self.assertEqual(c.request.call_count,1)
 def test_failed_backup_blocks_mutation(self):
  for xml in (XML.replace('200 OK','403 Forbidden'),XML.replace('END:VCARD','broken')):
   svc,c=self.service(xml)
   with self.assertRaises(ContactsError):svc._mutate(c,'DELETE','https://contacts.icloud.com/a.vcf')
   c.request.assert_not_called()
  svc,c=self.service()
  with patch('icloud_mcp.contact_backup.save_snapshot',side_effect=OSError('disk full')):
   with self.assertRaises(ContactsError):svc._mutate(c,'PUT','https://contacts.icloud.com/a.vcf',data=CARD)
  c.request.assert_not_called()
 def test_get_does_not_trigger_backup(self):
  svc,c=self.service();svc._mutate(c,'GET','https://contacts.icloud.com/a.vcf');svc._dav.assert_not_called()
 def test_every_mutator_uses_the_guard(self):
  import inspect
  for name in ('create','update','delete','create_group','update_group','delete_group'):
   self.assertIn('self._mutate(',inspect.getsource(getattr(ContactsService,name)))

from icloud_mcp.mail import MailService, MailError
from icloud_mcp.downloads import DownloadStore, RedactDownloadURLs
from urllib.parse import urlsplit
import logging
class DownloadTests(unittest.TestCase):
 def test_roundtrip_expiration_and_opaque_storage(self):
  with tempfile.TemporaryDirectory() as d:
   store=DownloadStore(d);r=store.create(b'\x00binary\xff','prueba ñ.pdf','https://example.invalid/icloud');token=r['download_url'].rsplit('/',1)[1]
   self.assertEqual(store.read(token),(b'\x00binary\xff','prueba ñ.pdf'))
   self.assertIsNone(store.read('../meta.json'))
   self.assertNotIn(token,' '.join(p.name for p in store.root.iterdir()))
   with patch('icloud_mcp.downloads.time.time',return_value=10**12):self.assertIsNone(store.read(token))
   self.assertEqual(list(store.root.iterdir()),[])
 def test_limit_and_no_https(self):
  with tempfile.TemporaryDirectory() as d:
   store=DownloadStore(d)
   with self.assertRaises(ValueError):store.create(b'x','a','http://example.invalid')
   with patch('icloud_mcp.downloads.MAX_ITEMS',1):
    store.create(b'x','a','https://example.invalid')
    with self.assertRaises(ValueError):store.create(b'y','b','https://example.invalid')
 def test_access_log_redaction(self):
  r=logging.LogRecord('uvicorn.access',20,'',1,'%s %s',('GET','/icloud/downloads/SECRET'),None)
  RedactDownloadURLs().filter(r);self.assertNotIn('SECRET',r.getMessage())

class ThreadTests(unittest.TestCase):
 def service(self, fail=None):
  s=MailService(Settings.from_env())
  messages={'INBOX':{1:('<root@x>','','')},'Sent':{2:('<reply@x>','','<root@x>')},'Archive/2025':{3:('<last@x>','','<reply@x>')},'Trash':{4:('<root@x>','','')},'Unrelated':{5:('<other@x>','','')}}
  class Client:
   folder='INBOX'
   def fetch(self,uids,items):
    out={}
    for u in uids:
     mid,refs,reply=messages[self.folder][u]
     out[u]={b'BODY[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)]':f'Message-ID: {mid}\r\nReferences: {refs}\r\nIn-Reply-To: {reply}\r\n'.encode()}
    return out
   def search(self,criteria):
    import re
    ids=re.findall('<[^>]+>',repr(criteria))
    return [u for u,v in messages[self.folder].items() if any(i in ' '.join(v) for i in ids)]
  c=Client();s.imap=lambda:contextlib.nullcontext(c);s.resolve_folder=lambda c,f:f
  s._list=lambda c:[([], '/',f) for f in messages]+[([b'\\Noselect'],'/','Not selectable')]
  def select(c,f,**kw):
   if f==fail: raise MailError('synthetic inaccessible')
   if kw.get('expect') not in (None,99): raise MailError('out of date')
   c.folder=f;return 99
  s._select=select
  s._summaries=lambda c,f,uids,uv:[{'folder':f,'uid':u,'uidvalidity':uv,'message_id':messages[f][u][0],'date':f'2026-01-0{u}T00:00:00+00:00'} for u in uids]
  return s
 def test_all_folders_transitive_and_deduplicated(self):
  d=self.service().get_thread('INBOX',1,uidvalidity=99)
  self.assertTrue(d['complete']);self.assertEqual(d['count'],3)
  self.assertEqual({m['message_id'] for m in d['messages']},{'<root@x>','<reply@x>','<last@x>'})
  self.assertEqual(len(d['messages'][0]['locations']),2)
  self.assertIn('Archive/2025',d['folders_searched']);self.assertNotIn('Not selectable',d['folders_searched'])
 def test_partial_explicit_and_uidvalidity(self):
  d=self.service('Archive/2025').get_thread('INBOX',1,uidvalidity=99)
  self.assertFalse(d['complete']);self.assertEqual(d['folders_not_read'],['Archive/2025'])
  with self.assertRaises(MailError):self.service().get_thread('INBOX',1,uidvalidity=7)
 def test_missing_ids_never_claims_complete(self):
  svc=self.service()
  with svc.imap() as c:c.fetch=lambda *a:{1:{b'BODY[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)]':b'Subject: no identifiers\r\n'}}
  d=svc.get_thread('INBOX',1,uidvalidity=99)
  self.assertFalse(d['complete']);self.assertEqual(d['count'],1);self.assertIn('no conversation identifiers',d['warning'])

import icalendar, recurring_ical_events
from datetime import datetime, timezone, date
from icloud_mcp.recurrence import truncate_future
from icloud_mcp.cal import CalendarService, CalendarError
ICS='BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:synthetic\r\nDTSTART:20261001T120000Z\r\nDTEND:20261001T130000Z\r\nRRULE:FREQ=DAILY;COUNT=4\r\nSUMMARY:Original\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n'
class RecurrenceTests(unittest.TestCase):
 def service(self,ics=ICS):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  s=CalendarService(replace(Settings.from_env(),data_dir=tmp.name));obj=Mock(data=ics,etag='old-etag',url='https://caldav.icloud.com/cal/original.ics');cal=Mock();cal.name='Home';cal.url='https://caldav.icloud.com/cal'
  from types import SimpleNamespace
  obj.client.request.return_value=SimpleNamespace(status=201,headers={'ETag':'new-etag'})
  cal.event_by_url.return_value=Mock(etag='old-etag')
  self.obj=obj;self.calendar=cal
  s._principal=lambda:contextlib.nullcontext(None);s._find=lambda *a:(cal,obj)
  s._refuse_invites=Mock();s._guests=Mock(return_value=[])
  self.saved=[];s._save=lambda obj,parsed,uid:self.saved.append(parsed)
  return s
 def test_following_update_keeps_past(self):
  s=self.service();s.update_event('synthetic',occurrence_start='2026-10-03T12:00:00Z',following=True,summary='Updated',start='2026-10-03T14:00:00Z')
  events=recurring_ical_events.of(self.saved[0]).between((2026,10,1),(2026,10,6))
  self.assertEqual([str(e['summary']) for e in events],['Original','Original','Updated','Updated'])
  self.assertEqual([e['dtstart'].dt.hour for e in events],[12,12,14,14])
 def test_following_delete_keeps_past(self):
  s=self.service();s.delete_event('synthetic',occurrence_start='2026-10-03T12:00:00Z',following=True)
  events=recurring_ical_events.of(self.saved[0]).between((2026,10,1),(2026,10,6));self.assertEqual(len(events),2)
 def test_missing_occurrence_and_changed_rule_refused(self):
  s=self.service()
  with self.assertRaises(CalendarError):s.update_event('synthetic',following=True,summary='x')
  with self.assertRaises(CalendarError):s.update_event('synthetic',occurrence_start='2026-10-03T12:00:00Z',rrule='FREQ=WEEKLY')
  self.assertEqual(self.saved,[])
 def test_all_day_truncate_and_exceptions(self):
  parsed=icalendar.Calendar.from_ical(ICS.replace('20261001T120000Z','20261001').replace('20261001T130000Z','20261002'))
  master=parsed.walk('VEVENT')[0];master.add('rdate',[date(2026,10,7)]);master.add('exdate',[date(2026,10,2)])
  truncate_future(parsed,master,date(2026,10,3))
  events=recurring_ical_events.of(parsed).between((2026,10,1),(2026,10,9));self.assertEqual(len(events),1)
 def test_later_single_edit_and_boundary_preserve_range(self):
  s=self.service();s.update_event('synthetic',occurrence_start='2026-10-02T12:00:00Z',following=True,summary='Updated',start='2026-10-02T14:00:00Z')
  range_ics=self.saved[-1].to_ical().decode();s=self.service(range_ics)
  s.update_event('synthetic',occurrence_start='2026-10-03T12:00:00Z',location='Here')
  events=recurring_ical_events.of(self.saved[-1]).between((2026,10,1),(2026,10,6))
  self.assertEqual([str(e['summary']) for e in events],['Original','Updated','Updated','Updated'])
  self.assertEqual([e['dtstart'].dt.hour for e in events],[12,14,14,14])
  s=self.service(range_ics);s.update_event('synthetic',occurrence_start='2026-10-02T12:00:00Z',summary='Only one')
  events=recurring_ical_events.of(self.saved[-1]).between((2026,10,1),(2026,10,6))
  self.assertEqual([str(e['summary']) for e in events],['Original','Only one','Updated','Updated'])
  s=self.service(range_ics);s.delete_event('synthetic',occurrence_start='2026-10-02T12:00:00Z')
  events=recurring_ical_events.of(self.saved[-1]).between((2026,10,1),(2026,10,6))
  self.assertEqual([e['dtstart'].dt.day for e in events],[1,3,4])
  self.assertEqual([e['dtstart'].dt.hour for e in events],[12,14,14])

class RecurrenceCompletionTests(unittest.TestCase):
 service = RecurrenceTests.service
 def expanded(self, parsed):
  return recurring_ical_events.of(parsed).between((2026,10,1),(2026,11,20))
 def test_split_daily_to_weekly_preserves_past_and_new_count(self):
  s=self.service();result=s.update_event('synthetic',following=True,occurrence_start='2026-10-03T12:00:00Z',rrule='FREQ=WEEKLY;COUNT=3')
  self.assertTrue(result['split_series']);self.assertNotEqual(result['uid'],'synthetic')
  future=icalendar.Calendar.from_ical(self.obj.client.request.call_args_list[0].args[2])
  self.assertEqual([e['dtstart'].dt.day for e in self.expanded(self.saved[0])],[1,2])
  self.assertEqual([e['dtstart'].dt.day for e in self.expanded(future)],[3,10,17])
  manifests=list((Path(s.s.data_dir)/'calendar-recovery').glob('*/manifest.json'))
  self.assertEqual(json.loads(manifests[0].read_text())['state'],'committed')
  self.assertEqual(manifests[0].stat().st_mode&0o777,0o600)
 def test_split_first_occurrence_keeps_uid_one_write(self):
  s=self.service();result=s.update_event('synthetic',following=True,occurrence_start='2026-10-01T12:00:00Z',rrule='FREQ=WEEKLY;COUNT=2')
  self.assertEqual(result['uid'],'synthetic');self.obj.client.request.assert_not_called()
  self.assertEqual([e['dtstart'].dt.day for e in self.expanded(self.saved[0])],[1,8])
 def test_split_remove_repetition_only_one_future_date(self):
  s=self.service();s.update_event('synthetic',following=True,occurrence_start='2026-10-03T12:00:00Z',rrule='')
  future=icalendar.Calendar.from_ical(self.obj.client.request.call_args_list[0].args[2])
  self.assertEqual([e['dtstart'].dt.day for e in self.expanded(future)],[3])
 def test_split_preserves_future_exception(self):
  s=self.service();s.update_event('synthetic',occurrence_start='2026-10-04T12:00:00Z',summary='Special',start='2026-10-04T15:00:00Z')
  s=self.service(self.saved[-1].to_ical());s.update_event('synthetic',following=True,occurrence_start='2026-10-03T12:00:00Z',rrule='FREQ=WEEKLY;COUNT=2')
  future=icalendar.Calendar.from_ical(self.obj.client.request.call_args_list[0].args[2])
  events=self.expanded(future)
  self.assertEqual([e['dtstart'].dt.day for e in events],[3,4,10])
  self.assertEqual(str(events[1]['summary']),'Special');self.assertEqual(events[1]['dtstart'].dt.hour,15)
 def test_boundary_skips_individual_override_and_stops_at_next_range(self):
  s=self.service();s.update_event('synthetic',occurrence_start='2026-10-02T12:00:00Z',following=True,summary='Range A')
  s=self.service(self.saved[-1].to_ical());s.update_event('synthetic',occurrence_start='2026-10-03T12:00:00Z',summary='Special')
  s=self.service(self.saved[-1].to_ical());s.update_event('synthetic',occurrence_start='2026-10-04T12:00:00Z',following=True,summary='Range B')
  s=self.service(self.saved[-1].to_ical());s.delete_event('synthetic',occurrence_start='2026-10-02T12:00:00Z')
  self.assertEqual([str(e['summary']) for e in self.expanded(self.saved[-1])],['Original','Special','Range B'])
 def test_boundary_final_occurrence_has_no_extra_date(self):
  s=self.service();s.update_event('synthetic',occurrence_start='2026-10-04T12:00:00Z',following=True,summary='Last')
  s=self.service(self.saved[-1].to_ical());s.delete_event('synthetic',occurrence_start='2026-10-04T12:00:00Z')
  self.assertEqual([e['dtstart'].dt.day for e in self.expanded(self.saved[-1])],[1,2,3])
 def test_split_failure_rolls_back_only_if_original_unchanged(self):
  s=self.service();s._save=Mock(side_effect=RuntimeError('write refused'))
  with self.assertRaisesRegex(CalendarError,'original is unchanged'):
   s.update_event('synthetic',following=True,occurrence_start='2026-10-03T12:00:00Z',rrule='FREQ=WEEKLY')
  self.assertEqual([c.args[1] for c in self.obj.client.request.call_args_list],['PUT','DELETE'])
  self.assertEqual(self.obj.client.request.call_args.args[3]['If-Match'],'new-etag')
 def test_split_conflict_or_timeout_never_deletes_uncertain_state(self):
  s=self.service();s._save=Mock(side_effect=TimeoutError());self.calendar.event_by_url.return_value.etag='concurrently-changed'
  with self.assertRaisesRegex(CalendarError,'do not repeat'):
   s.update_event('synthetic',following=True,occurrence_start='2026-10-03T12:00:00Z',rrule='FREQ=WEEKLY')
  self.assertEqual(self.obj.client.request.call_count,1)
 def test_split_creation_timeout_and_missing_etag_fail_closed(self):
  s=self.service();self.obj.etag=None
  with self.assertRaisesRegex(CalendarError,'ETag'):
   s.update_event('synthetic',following=True,occurrence_start='2026-10-03T12:00:00Z',rrule='FREQ=WEEKLY')
  self.obj.client.request.assert_not_called()
  s=self.service();self.obj.client.request.side_effect=TimeoutError()
  with self.assertRaisesRegex(CalendarError,'do not repeat'):
   s.update_event('synthetic',following=True,occurrence_start='2026-10-03T12:00:00Z',rrule='FREQ=WEEKLY')
  self.assertEqual(self.saved,[]);self.obj.client.request.assert_called_once()
 def test_boundary_all_day_and_dst(self):
  s=self.service(ICS.replace('20261001T120000Z','20261001').replace('20261001T130000Z','20261002'))
  s.update_event('synthetic',occurrence_start='2026-10-02',following=True,summary='Range')
  s=self.service(self.saved[-1].to_ical());s.delete_event('synthetic',occurrence_start='2026-10-02')
  self.assertEqual([e['dtstart'].dt.day for e in self.expanded(self.saved[-1])],[1,3,4])
  ics=ICS.replace('DTSTART:20261001T120000Z','DTSTART;TZID=America/New_York:20261031T120000').replace('DTEND:20261001T130000Z','DTEND;TZID=America/New_York:20261031T130000')
  s=self.service(ics);s.update_event('synthetic',occurrence_start='2026-10-31T12:00:00-04:00',following=True,start='2026-10-31T14:00:00-04:00',timezone_name='America/New_York')
  s=self.service(self.saved[-1].to_ical());s.update_event('synthetic',occurrence_start='2026-10-31T12:00:00-04:00',summary='Only boundary',timezone_name='America/New_York')
  events=self.expanded(self.saved[-1]);self.assertEqual([e['dtstart'].dt.hour for e in events],[14,14,14,14])

class InvitationTests(unittest.TestCase):
 service = RecurrenceTests.service
 def invitation(self, own=True, organizer='organizer@example.invalid'):
  return ICS.replace('SUMMARY:Original', 'SUMMARY:Original\r\nORGANIZER:mailto:'+organizer+'\r\nATTENDEE;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:' + ('test@example.invalid' if own else 'other@example.invalid'))
 def test_rsvp_changes_only_owner_and_invalid_cases_write_nothing(self):
  s=self.service(self.invitation());s.s=replace(s.s,allow_calendar_invites=True)
  r=s.rsvp('synthetic','accepted');self.assertEqual(r['answered'],'accepted')
  ev=self.saved[-1].walk('VEVENT')[0];self.assertEqual(ev['attendee'].params['PARTSTAT'],'ACCEPTED');self.assertNotIn('RSVP',ev['attendee'].params)
  for ics in (self.invitation(own=False),self.invitation(organizer='test@example.invalid')):
   s=self.service(ics);s.s=replace(s.s,allow_calendar_invites=True)
   with self.assertRaises(CalendarError):s.rsvp('synthetic','accepted')
   self.assertEqual(self.saved,[])
 def test_invitation_gate_and_invalid_answer(self):
  s=self.service(self.invitation());s.s=replace(s.s,allow_calendar_invites=False)
  with self.assertRaises(CalendarError):s.rsvp('synthetic','accepted')
  with self.assertRaises(CalendarError):s.rsvp('synthetic','something else')
  self.assertEqual(self.saved,[])
 def test_rsvp_one_range_boundary_does_not_answer_future(self):
  s=self.service(self.invitation());s.update_event('synthetic',occurrence_start='2026-10-02T12:00:00Z',following=True,summary='Range')
  s=self.service(self.saved[-1].to_ical());s.s=replace(s.s,allow_calendar_invites=True)
  s.rsvp('synthetic','accepted',occurrence_start='2026-10-02T12:00:00Z')
  events=recurring_ical_events.of(self.saved[-1]).between((2026,10,1),(2026,10,6))
  self.assertEqual([e['attendee'].params['PARTSTAT'] for e in events],['NEEDS-ACTION','ACCEPTED','NEEDS-ACTION','NEEDS-ACTION'])

class ImportedReplyTests(unittest.TestCase):
 service = RecurrenceTests.service
 invitation = InvitationTests.invitation
 def setup_reply(self):
  s=self.service(self.invitation());self.obj.schedule_tag=None
  s.s=replace(s.s,allow_calendar_invites=True,allow_send=True,require_approval=False)
  mail=Mock();mail.imap.return_value=contextlib.nullcontext(Mock());mail._deliver.return_value={'status':'sent'}
  return s,mail
 def test_imported_reply_is_standard_imip_and_deduplicated(self):
  s,mail=self.setup_reply()
  with patch('icloud_mcp.mail.MailService',return_value=mail):
   r=s.rsvp('synthetic','accepted');self.assertEqual(r['reply_delivery'],'sent')
   msg=mail._deliver.call_args.args[1]
   self.assertEqual(str(msg['To']),'organizer@example.invalid')
   calendar_part=next(p for p in msg.walk() if p.get_content_type()=='text/calendar')
   self.assertEqual(calendar_part.get_param('method'),'REPLY')
   parsed=icalendar.Calendar.from_ical(calendar_part.get_content());ev=parsed.walk('VEVENT')[0]
   self.assertEqual(str(parsed['method']),'REPLY');self.assertEqual(str(ev['uid']),'synthetic')
   self.assertEqual(ev['attendee'].params['PARTSTAT'],'ACCEPTED');self.assertNotIn('SCHEDULE-AGENT',ev['organizer'].params)
   self.obj.data=self.saved[-1].to_ical().decode()
   r=s.rsvp('synthetic','accepted');self.assertTrue(r['reply_already_sent']);mail._deliver.assert_called_once()
   self.obj.data=self.saved[-1].to_ical().decode();s.rsvp('synthetic','tentative');self.assertEqual(mail._deliver.call_count,2)
 def test_uncertain_reply_is_not_resent(self):
  s,mail=self.setup_reply();mail._deliver.side_effect=TimeoutError()
  with patch('icloud_mcp.mail.MailService',return_value=mail):
   with self.assertRaisesRegex(CalendarError,'Do not retry'):s.rsvp('synthetic','accepted')
   self.obj.data=self.saved[-1].to_ical().decode()
   r=s.rsvp('synthetic','accepted');self.assertEqual(r['reply_delivery'],'unknown');mail._deliver.assert_called_once()
 def test_imported_reply_respects_send_gate(self):
  s,mail=self.setup_reply();s.s=replace(s.s,allow_send=False)
  with patch('icloud_mcp.mail.MailService',return_value=mail):
   with self.assertRaisesRegex(CalendarError,'Nothing changed'):s.rsvp('synthetic','accepted')
  self.assertEqual(self.saved,[]);mail._deliver.assert_not_called()
