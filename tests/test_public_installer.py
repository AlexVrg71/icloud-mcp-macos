"""Public installer contracts with fake homes, mock processes and synthetic secrets."""
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch, Mock

spec = importlib.util.spec_from_file_location('manage', Path(__file__).parents[1] / 'scripts/manage.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class PublicInstallerTests(unittest.TestCase):
    def cfg(self, **kw):
        return {**m.defaults(), 'username':'test@example.invalid', **kw}
    def test_root_is_user_relative_and_independent(self):
        root=m.default_root(Path('/synthetic home'))
        self.assertEqual(root,Path('/synthetic home/Library/Application Support/iCloud-MCP-macOS'))
    def test_defaults_read_only_no_send_no_helper(self):
        cfg=self.cfg();env=m.environment(cfg,Path('/synthetic'))
        for name in ('ALLOW_SEND','ALLOW_CALENDAR_INVITES','ENABLE_EVENTKIT_REMINDERS','ENABLE_REMINDERS','ENABLE_NOTES','ENABLE_DRIVE','ENABLE_IMESSAGE'):
            self.assertEqual(env[name],'false')
        self.assertEqual(env['READ_ONLY'],'true');self.assertEqual(env['MCP_HOST'],'127.0.0.1')
    def test_inherited_secrets_and_paths_are_dropped(self):
        env=m.environment(self.cfg(),Path('/synthetic'),{'ICLOUD_APP_PASSWORD':'synthetic','MCP_OWNER_PASSWORD':'synthetic','DATA_DIR':'/elsewhere','ENABLE_DRIVE':'true','HOME':'/synthetic'})
        self.assertNotIn('ICLOUD_APP_PASSWORD',env);self.assertNotIn('MCP_OWNER_PASSWORD',env)
        self.assertEqual(env['DATA_DIR'],'/synthetic/data');self.assertEqual(env['ENABLE_DRIVE'],'false')
    def test_explicit_write_policies(self):
        env=m.environment(self.cfg(read_only=False,allow_send=True,allow_calendar_invites=True,chat_approvals=True,reminders=True),Path('/synthetic'))
        self.assertEqual(env['ALLOW_SEND'],'true');self.assertEqual(env['SEND_REQUIRES_APPROVAL'],'false')
        self.assertEqual(env['EVENTKIT_REMINDERS_SOCKET'],'/synthetic/data/eventkit/reminders.sock')
    def test_secret_keys_unknown_fields_rejected(self):
        with self.assertRaises(ValueError):m.validate(self.cfg(password='synthetic'))
    def test_url_credentials_plaintext_and_fragments_rejected(self):
        for url in ('http://example.invalid','https://test:secret@example.invalid','https://example.invalid/#secret','https://example.invalid/?token=x','https://example.invalid/a/../b'):
            with self.subTest(url=url),self.assertRaises(ValueError):m.validate(self.cfg(public_url=url))
    def test_timezone_boolean_and_port_validation(self):
        for kw in ({'timezone':'not-a-zone'},{'port':True},{'port':80},{'read_only':'false'},{'username':'bad\n@example.invalid'},{'allow_send':True}):
            with self.subTest(kw=kw),self.assertRaises(ValueError):m.validate(self.cfg(**kw))
    def test_existing_install_never_replaced(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'run') as run:
            with self.assertRaises(ValueError):m.install(Path(d),True)
            run.assert_not_called()
    def test_launch_agent_spaces_use_argument_arrays(self):
        root=Path('/synthetic home/Library/Application Support/iCloud-MCP-macOS')
        for helper in (True,False):
            item=plistlib.loads(plistlib.dumps(m.plist(root,helper)))
            self.assertIsInstance(item['ProgramArguments'],list)
            self.assertEqual(item['LimitLoadToSessionType'],'Aqua')
            self.assertNotIn('EnvironmentVariables',item)
            self.assertNotIn('/bin/sh',item['ProgramArguments'])
    def test_keychain_secret_only_goes_to_stdin(self):
        with patch.object(m.subprocess,'run') as run:
            m.store_secret(Path('/synthetic'),m.APPLE_SERVICE,'test@example.invalid','synthetic-hidden-secret')
            args,kw=run.call_args
            self.assertNotIn('synthetic-hidden-secret',args[0]);self.assertEqual(kw['input'],b'synthetic-hidden-secret')
    def test_password_mismatch_and_empty_do_not_store(self):
        for values in (['',''],['one','two']):
            with patch.object(m.sys.stdin,'isatty',return_value=True),patch.object(m.getpass,'getpass',side_effect=values),self.assertRaises(ValueError):
                m.password_twice('Test: ',12)
    def test_private_config_roundtrip_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'config.json'
            m.write_private(p,json.dumps(self.cfg()).encode());self.assertEqual(p.stat().st_mode&0o777,0o600)
            self.assertEqual(m.read_config(root),self.cfg())
            target=root/'target';p.rename(target);p.symlink_to(target)
            with self.assertRaises(ValueError):m.read_config(root)
    def test_run_retrieves_oauth_without_logging_and_uses_installed_python(self):
        root=Path('/synthetic');cfg=self.cfg(public_url='https://example.invalid')
        with patch.object(m,'require_installed'),patch.object(m,'read_config',return_value=cfg),patch.object(m.subprocess,'run',return_value=Mock(returncode=0,stdout=b'synthetic-owner-secret\n')),patch.object(m.os,'execve') as ex:
            m.run(root,False)
            binary,argv,env=ex.call_args.args
            self.assertEqual(binary,'/synthetic/.venv/bin/python');self.assertNotIn('synthetic-owner-secret',argv)
            self.assertEqual(env['MCP_OWNER_PASSWORD'],'synthetic-owner-secret')
    def test_stdio_does_not_request_oauth(self):
        with patch.object(m,'require_installed'),patch.object(m,'read_config',return_value=self.cfg()),patch.object(m.subprocess,'run') as run,patch.object(m.os,'execve') as ex:
            m.run(Path('/synthetic'),True)
            run.assert_not_called();self.assertIn('--stdio',ex.call_args.args[1]);self.assertNotIn('MCP_OWNER_PASSWORD',ex.call_args.args[2])
    def test_installer_matches_helper_identity_and_root(self):
        root=Path(__file__).parents[1]
        info=plistlib.loads((root/'mac-reminders/Info.plist').read_bytes())
        self.assertEqual(info['CFBundleIdentifier'],m.HELPER_LABEL)
        text=(root/'mac-reminders/Sources/ICloudMCPReminders/main.swift').read_text()
        self.assertIn(m.APP+'/data/eventkit',text)
    def test_catalog_settings_from_public_environment(self):
        from icloud_mcp.config import Settings
        from icloud_mcp.server import create_server
        import asyncio
        env=m.environment(self.cfg(reminders=True),Path('/synthetic'))
        env.update(ICLOUD_KEYCHAIN='false',ICLOUD_APP_PASSWORD='synthetic')
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{**env,'DATA_DIR':d},clear=True):
            from dataclasses import replace
            settings=replace(Settings.from_env(), local_mode=True)
            self.assertEqual(settings.eventkit_socket,env['EVENTKIT_REMINDERS_SOCKET'])
            server,_=create_server(settings)
            tools=asyncio.run(server.list_tools());names={t.name for t in tools}
            self.assertIn('reminders_list_lists',names);self.assertNotIn('reminders_create_reminder',names)
            self.assertFalse(any(n.startswith(('drive_','imessage_','notes_')) for n in names))

    def test_install_only_builds_and_copies_without_activating(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'new'
            with patch.object(m.shutil,'which',return_value='/synthetic/swiftc'),patch.object(m.subprocess,'run') as run,patch.object(m.shutil,'copy2'),patch.object(m.shutil,'copytree'):
                m.install(root,True)
                commands=[call.args[0] for call in run.call_args_list]
                self.assertEqual(len(commands),4)
                self.assertFalse(any('launchctl' in str(c) or '/usr/bin/open' in str(c) or 'security' in str(c) for c in commands))
                self.assertFalse((root/'config.json').exists())
    def test_http_without_url_never_reads_keychain(self):
        with patch.object(m,'require_installed'),patch.object(m,'read_config',return_value=self.cfg()),patch.object(m.subprocess,'run') as run,self.assertRaises(ValueError):
            m.run(Path('/synthetic'),False)
        run.assert_not_called()
    def test_hidden_input_failure_does_not_fall_back_to_echo(self):
        with patch.object(m.sys.stdin,'isatty',return_value=True),patch.object(m.getpass,'getpass',side_effect=m.getpass.GetPassWarning('synthetic')) as get,self.assertRaises(ValueError):
            m.password_twice('Test: ',12)
        self.assertEqual(get.call_count,1)
    def test_start_refuses_existing_agent_before_any_subprocess(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);root=m.default_root(home)
            agent=home/'Library/LaunchAgents'/(m.SERVER_LABEL+'.plist');agent.parent.mkdir(parents=True);agent.write_bytes(b'existing')
            with patch.object(m.Path,'home',return_value=home),patch.object(m,'require_installed'),patch.object(m,'read_config',return_value=self.cfg(public_url='https://example.invalid')),patch.object(m.subprocess,'run') as run:
                with self.assertRaises(ValueError):m.start(root,False)
                run.assert_not_called();self.assertEqual(agent.read_bytes(),b'existing')
    def test_stop_does_not_touch_an_unrecognized_agent(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);agent=home/'Library/LaunchAgents'/(m.SERVER_LABEL+'.plist');agent.parent.mkdir(parents=True)
            agent.write_bytes(plistlib.dumps({'Label':m.SERVER_LABEL,'ProgramArguments':['/another/program']}))
            with patch.object(m.Path,'home',return_value=home),patch.object(m.subprocess,'run') as run:
                with self.assertRaises(ValueError):m.stop(False)
                run.assert_not_called();self.assertTrue(agent.exists())

if __name__=='__main__':unittest.main()
