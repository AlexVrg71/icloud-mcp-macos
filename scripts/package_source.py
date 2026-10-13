#!/usr/bin/env python3
"""Build a source-only zip with a SHA-256 inventory, excluding development/runtime state."""
import hashlib
from pathlib import Path
import zipfile
from check_public_tree import scan

root=Path(__file__).resolve().parents[1]
files,findings=scan(root)
if findings:
    raise SystemExit('Source hygiene check failed. Run check_public_tree.py; no archive written.')
destination=root/'dist/icloud-mcp-macos-0.1.0b1-source.zip'
destination.parent.mkdir(exist_ok=True)
manifest=[]
with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        name=path.relative_to(root).as_posix();data=path.read_bytes()
        info=zipfile.ZipInfo('icloud-mcp-macos/'+name,date_time=(1980,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=(0o100755 if path.stat().st_mode&0o111 else 0o100644)<<16
        archive.writestr(info,data)
        manifest.append(hashlib.sha256(data).hexdigest()+'  '+name)
    archive.writestr('icloud-mcp-macos/SHA256SUMS','\n'.join(manifest)+'\n')
print(destination.name)
print('sha256:',hashlib.sha256(destination.read_bytes()).hexdigest())
print('source files:',len(files))
