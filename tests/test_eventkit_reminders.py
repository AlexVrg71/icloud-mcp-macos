import asyncio
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.update(ICLOUD_USERNAME='test@example.invalid', ICLOUD_APP_PASSWORD='synthetic', ICLOUD_KEYCHAIN='false',
                  WARMUP_ON_START='false', ENABLE_EVENTKIT_REMINDERS='false')
from icloud_mcp.config import Settings
from icloud_mcp.bridge import BridgeError
from icloud_mcp.eventkit_reminders import EventKitClient
from icloud_mcp.server import create_server

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='/tmp', prefix='gr-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.root.chmod(0o700); self.path = str(self.root/'r.sock')
        self.client = EventKitClient(self.path, timeout=.15)
    def fake(self, reply, delay=0):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); sock.bind(self.path); os.chmod(self.path,0o600); sock.listen(1)
        self.received=[]
        def serve():
            try:
                c,_=sock.accept()
                with c:
                    self.received.append(json.loads(c.recv(65536)))
                    time.sleep(delay)
                    try:c.sendall(json.dumps(reply).encode()+b'\n')
                    except BrokenPipeError:pass
            finally:sock.close()
        thread=threading.Thread(target=serve,daemon=True);thread.start();self.addCleanup(lambda:thread.join(1))
    def test_missing_helper_never_dispatches(self):
        with self.assertRaisesRegex(BridgeError,'offline'):self.client.call('create',title='Synthetic')
    def test_status_offline_is_explicit_failure(self):
        r=self.client.status();self.assertFalse(r['ok']);self.assertFalse(r['online']);self.assertEqual(r['authorization'],'unknown')
    def test_denied_permission_is_not_empty_list(self):
        self.fake({'ok':False,'error':{'code':'permission_denied','message':'Owner must grant access'}})
        with self.assertRaisesRegex(BridgeError,'permission_denied'):self.client.call('lists')
    def test_success_preserves_pagination_and_uncertain_sync(self):
        self.fake({'ok':True,'result':{'reminders':[], 'complete':False,'next_offset':10,'sync_status':'not_verified'}})
        r=self.client.call('search',completed='completed',offset=0);self.assertFalse(r['complete']);self.assertEqual(r['next_offset'],10)
        self.assertEqual(self.received[0]['completed'],'completed')
    def test_timed_out_write_reports_uncertainty_and_only_one_dispatch(self):
        self.fake({'ok':True,'result':{}},delay=.3)
        with self.assertRaisesRegex(BridgeError,'SAME request_id'):self.client.call('create',request_id='test')
        self.assertEqual(len(self.received),1)
    def test_malformed_write_reply_never_claims_not_created(self):
        self.fake({'wrong':'shape'})
        with self.assertRaisesRegex(BridgeError,'outcome_unknown'):self.client.call('create')
    def test_socket_permissions_fail_closed(self):
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.addCleanup(sock.close);sock.bind(self.path);os.chmod(self.path,0o666)
        with self.assertRaisesRegex(BridgeError,'unsafe_reminders_socket'):self.client.call('status')
    def test_not_an_exec_channel(self):
        with self.assertRaisesRegex(BridgeError,'Unsupported'):self.client.call('request_permission')

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=replace(Settings.from_env(),local_mode=True,read_only=False,tools=("mail","calendar","contacts"),data_dir=self.temp.name,enable_reminders=False,
                          enable_notes=False,enable_drive=False,enable_maps=False,enable_imessage=False,enable_health=False,shortcuts_allow=())
    def catalog(self,s):
        if s.enable_eventkit_reminders: s=replace(s,tools=s.tools+("reminders","icloud_get_time"))
        m,_=create_server(s);return m,{t.name:t for t in asyncio.run(m.list_tools())}
    def test_existing_50_tools_and_schemas_unchanged_when_enabled(self):
        _,before=self.catalog(self.base);m,after=self.catalog(replace(self.base,enable_eventkit_reminders=True))
        self.assertEqual(len(before),50);self.assertEqual(len(after),59)
        for n,t in before.items():self.assertEqual(t.model_dump(),after[n].model_dump(),n)
        self.assertNotIn('icloud_get_helper_status',after)
        self.assertTrue(hasattr(m,'_icloud_eventkit'));self.assertFalse(hasattr(m,'_icloud_bridge'))
    def test_new_schema_approvals_ids_and_timezone(self):
        _,ts=self.catalog(replace(self.base,enable_eventkit_reminders=True))
        for n in ('create','update','complete','delete'):
            tool=ts['reminders_'+n+'_reminder'];req=tool.input_schema['required']
            self.assertIn('request_id',req);self.assertIn('confirmed',req);self.assertFalse(tool.annotations.read_only_hint)
        self.assertTrue(ts['reminders_delete_reminder'].annotations.destructive_hint)
        self.assertIn('alarm',ts['reminders_create_reminder'].input_schema['required'])
        self.assertIn('timezone',ts['reminders_create_reminder'].input_schema['properties'])
        for n in ('reminders_get_status','reminders_list_lists','reminders_list_reminders','reminders_get_reminder'):
            self.assertTrue(ts[n].annotations.read_only_hint)
    def test_readonly_omits_mutations(self):
        _,ts=self.catalog(replace(self.base,enable_eventkit_reminders=True,read_only=True))
        self.assertIn('reminders_get_reminder',ts);self.assertNotIn('reminders_create_reminder',ts);self.assertNotIn('reminders_delete_reminder',ts)
    def test_backend_collision_rejected(self):
        with self.assertRaisesRegex(SystemExit,'Choose one'):
            replace(self.base,enable_reminders=True,enable_eventkit_reminders=True)._validate_bridge_and_areas()
    def test_health_includes_disabled_or_denied_local_access_without_prompt(self):
        s=replace(self.base,enable_eventkit_reminders=True,enable_mail=False,enable_calendar=False,enable_contacts=False)
        m,_=self.catalog(s)
        with patch.object(m._icloud_eventkit,'call',return_value={'ok':False,'online':True,'authorization':'denied'}) as call:
            r=m._icloud_health();self.assertFalse(r['ok']);self.assertEqual(r['areas']['reminders']['authorization'],'denied');call.assert_called_once_with('status')
    def test_instructions_distinguish_local_sync_and_example(self):
        from icloud_mcp.instructions import build_instructions
        txt=build_instructions(replace(self.base,enable_eventkit_reminders=True))
        self.assertIn('examples never authorize creation',txt);self.assertIn('local_saved is separate',txt)

if __name__=='__main__':unittest.main()
