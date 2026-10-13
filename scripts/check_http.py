import asyncio,os,tempfile
from pathlib import Path
import httpx
os.environ.update(ICLOUD_USERNAME='test@example.invalid',ICLOUD_APP_PASSWORD='synthetic',ICLOUD_KEYCHAIN='false',MCP_OWNER_PASSWORD='synthetic-owner-password',MCP_PUBLIC_URL='https://example.invalid/icloud',READ_ONLY='false',ALLOW_SEND='true',SEND_REQUIRES_APPROVAL='false',TOOLS='mail,calendar,contacts',WARMUP_ON_START='false')
from icloud_mcp.config import Settings
from icloud_mcp.server import create_server,build_app
from icloud_mcp.downloads import DownloadStore
async def main():
 with tempfile.TemporaryDirectory() as d:
  os.environ['DATA_DIR']=d;s=Settings.from_env();m,_=create_server(s)
  listed=await m.list_tools();tools={t.name:t for t in listed}
  for n in ('mail_send_message','mail_reply_to_message','mail_forward_message','mail_send_draft'):
   assert tools[n].annotations.read_only_hint is False and tools[n].annotations.destructive_hint is True
  assert tools['mail_get_attachment_download'].annotations.read_only_hint
  for n in ('calendar_update_event','calendar_delete_event'):
   assert 'following' in tools[n].input_schema['properties']
  link=DownloadStore(d).create(b'\x00binary\xff','archivo ñ.pdf',s.public_url)['download_url'];token=link.rsplit('/',1)[1]
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(s,m)),base_url='https://example.invalid') as c:
   r=await c.get('/downloads/'+token);assert r.status_code==200 and r.content==b'\x00binary\xff'
   assert r.headers['cache-control']=='no-store' and '%C3%B1.pdf' in r.headers['content-disposition']
   assert (await c.get('/downloads/'+'x'*43)).status_code==404
   assert (await c.get('/mcp')).status_code==401
  print('PASS: catalog',len(tools),'tools; write approval annotations; following schema; download byte fidelity/headers/invalid link; MCP remains OAuth protected.')
asyncio.run(main())
