import asyncio, os, tempfile, secrets, hashlib, base64
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs
import httpx
os.environ.update(ICLOUD_USERNAME='test@example.invalid', ICLOUD_APP_PASSWORD='synthetic-test-only', ICLOUD_KEYCHAIN='false', MCP_OWNER_PASSWORD='synthetic-owner-only', TOOLS='mail,calendar,contacts', READ_ONLY='true', WARMUP_ON_START='false')
from icloud_mcp.config import Settings
from icloud_mcp.server import create_server, build_app

class Form(HTMLParser):
    action = None
    def handle_starttag(self, tag, attrs):
        if tag == 'form': self.action = dict(attrs)['action']

async def check(prefix):
    with tempfile.TemporaryDirectory() as data:
        public = 'https://example.invalid' + prefix
        os.environ.update(MCP_PUBLIC_URL=public, DATA_DIR=data)
        settings = Settings.from_env(); settings.validate_for_server()
        mcp, _ = create_server(settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app(settings, mcp)), base_url='https://example.invalid') as c:
            callback = 'https://chatgpt.com/connector/oauth/synthetic'
            r = await c.post('/register', json=dict(client_name='Synthetic regression test', redirect_uris=[callback], grant_types=['authorization_code','refresh_token'], response_types=['code'], scope='icloud', token_endpoint_auth_method='client_secret_post'))
            assert r.status_code == 201
            client = r.json()
            verifier = secrets.token_urlsafe(32)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            params=dict(client_id=client['client_id'], redirect_uri=callback, response_type='code', scope='icloud', code_challenge=challenge, code_challenge_method='S256', state='synthetic')
            r=await c.get('/authorize', params=params)
            assert r.status_code == 302
            location=urlsplit(r.headers['location'])
            pid=parse_qs(location.query)['p'][0]
            r=await c.get('/login', params={'p':pid})
            parser=Form(); parser.feed(r.text)
            assert parser.action == public + '/login', parser.action
            # Model a reverse proxy configured to strip the public prefix.
            target=urlsplit(parser.action).path.removeprefix(prefix) if prefix else urlsplit(parser.action).path
            r=await c.post(target, data=dict(p=pid, password='wrong-synthetic', action='approve'))
            assert r.status_code == 401
            r=await c.post(target, data=dict(p=pid, password=settings.owner_password, action='approve'))
            assert r.status_code == 302
            redirect=urlsplit(r.headers['location']); assert redirect.hostname == 'chatgpt.com'
            query=parse_qs(redirect.query); assert query['state']==['synthetic']
            token_data=dict(grant_type='authorization_code', code=query['code'][0], redirect_uri=callback, client_id=client['client_id'], client_secret=client['client_secret'], code_verifier=verifier)
            r=await c.post('/token', data=token_data)
            assert r.status_code == 200, r.status_code
            assert r.json()['access_token'] and r.json()['refresh_token']
            assert (await c.post('/token', data=token_data)).status_code == 400
            assert (await c.get('/mcp')).status_code == 401
            r=await c.get('/authorize', params=params)
            pid=parse_qs(urlsplit(r.headers['location']).query)['p'][0]
            r=await c.post(target, data=dict(p=pid, action='deny'))
            assert r.status_code == 302 and parse_qs(urlsplit(r.headers['location']).query)['error']==['access_denied']
            print(f'PASS {prefix or "/"}: form route, password rejection, approval, PKCE token exchange, code replay rejection, denial, unauthenticated MCP.')

async def main():
    await check('')
    await check('/icloud')
asyncio.run(main())
