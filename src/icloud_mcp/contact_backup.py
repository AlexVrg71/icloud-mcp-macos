"""Private, durable snapshots. No contact mutation may precede a verified snapshot."""
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def save_snapshot(data_dir: str, books: list[dict], operation: str) -> str:
    root = Path(data_dir) / "contact-backups"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=root))
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ-") + uuid.uuid4().hex[:8]
    manifest = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "operation": operation, "books": [], "cards": 0}
    def write(filename, payload):
        path = stage / filename
        with path.open("xb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(payload); f.flush(); os.fsync(f.fileno())
        digest = hashlib.sha256(payload).hexdigest()
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise OSError("Contact backup verification failed")
        return digest
    try:
        for i, book in enumerate(books):
            cards = book["cards"]
            payload = ("\r\n".join(c["raw"].strip() for c in cards) + ("\r\n" if cards else "")).encode()
            filename = f"book-{i+1}.vcf"
            digest = write(filename, payload)
            manifest["books"].append({"url": book["url"], "file": filename, "sha256": digest,
                                      "cards": [{k:v for k,v in c.items() if k != "raw"} for c in cards]})
            manifest["cards"] += len(cards)
        write("manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2)+"\n").encode())
        os.rename(stage, root / name)
        fd = os.open(root, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
        return name
    finally:
        if stage.exists(): shutil.rmtree(stage)
