"""Short-lived attachment capabilities. Tokens are never persisted or access-logged."""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import threading
import time
from urllib.parse import quote

_LOCK = threading.RLock()
TTL = 15 * 60
MAX_ITEMS = 32
class RedactDownloadURLs(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(re.sub(r'/downloads/[^ /?]+', '/downloads/[redacted]', x) if isinstance(x,str) else x for x in record.args)
        return True

class DownloadStore:
    def __init__(self, data_dir):
        self.root = Path(data_dir) / 'attachment-downloads'
    def _cleanup(self):
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.root.chmod(0o700)
        for path in self.root.iterdir():
            if not path.is_dir() or not re.fullmatch(r'[a-f0-9]{64}', path.name): continue
            try: expired=json.loads((path/'meta.json').read_text())['expires_at'] <= time.time()
            except (OSError,ValueError,KeyError): expired=True
            if expired: shutil.rmtree(path)
    def create(self, data, filename, public_url):
        if not public_url.startswith('https://'): raise ValueError('An HTTPS public URL is required for attachment downloads.')
        token=secrets.token_urlsafe(32); key=hashlib.sha256(token.encode()).hexdigest()
        with _LOCK:
            self._cleanup()
            if len(list(self.root.iterdir())) >= MAX_ITEMS: raise ValueError('Attachment download limit reached; wait for existing links to expire.')
            folder=self.root/key; folder.mkdir(mode=0o700)
            meta={'filename':filename, 'expires_at':time.time()+TTL, 'sha256':hashlib.sha256(data).hexdigest()}
            try:
                for name,payload in [('content.bin',data),('meta.json',json.dumps(meta).encode())]:
                    with (folder/name).open('xb') as f:
                        os.fchmod(f.fileno(),0o600);f.write(payload);f.flush();os.fsync(f.fileno())
            except Exception:
                shutil.rmtree(folder);raise
        return {'download_url':public_url.rstrip('/')+'/downloads/'+token,'expires_in_seconds':TTL,
                'download_notice':'Anyone holding this link can download this attachment for 15 minutes. It expires automatically; do not share it beyond the intended recipient.'}
    def read(self, token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token): return None
        with _LOCK:
            self._cleanup()
            folder=self.root/hashlib.sha256(token.encode()).hexdigest()
            try:
                meta=json.loads((folder/'meta.json').read_text()); data=(folder/'content.bin').read_bytes()
            except (OSError,ValueError): return None
            if meta['expires_at'] <= time.time() or hashlib.sha256(data).hexdigest()!=meta['sha256']: return None
            return data,meta['filename']

def register_download_routes(mcp, settings):
    from starlette.responses import Response
    import asyncio
    logging.getLogger('uvicorn.access').addFilter(RedactDownloadURLs())
    store=DownloadStore(settings.data_dir)
    @mcp.custom_route('/downloads/{token}',methods=['GET'])
    async def download(request):
        item=await asyncio.to_thread(store.read,request.path_params['token'])
        if item is None: return Response('Link invalid or expired.',status_code=404,headers={'Cache-Control':'no-store'})
        data,filename=item
        return Response(data,media_type='application/octet-stream',headers={
            'Content-Disposition':"attachment; filename=attachment; filename*=UTF-8''"+quote(filename,safe=''),
            'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"default-src 'none'; sandbox"})
