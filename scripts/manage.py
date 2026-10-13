#!/usr/bin/env python3
"""Opt-in, single-owner macOS installation. No credentials in files or argv."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import plistlib
import platform
import shutil
import subprocess
import sys
import warnings
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

APP = "iCloud-MCP-macOS"
SERVER_LABEL = "org.icloudmcp.macos.server"
HELPER_LABEL = "org.icloudmcp.macos.reminders"
APPLE_SERVICE = "icloud-mcp-macos.apple"
OWNER_SERVICE = "icloud-mcp-macos.oauth"
SOURCE = Path(__file__).resolve().parents[1]


def default_root(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library/Application Support" / APP


def defaults() -> dict:
    return dict(username="", email_address="", timezone="UTC", public_url="", port=8876,
                read_only=True, allow_send=False, allow_calendar_invites=False,
                chat_approvals=False, reminders=False)


def validate(cfg: dict) -> dict:
    if set(cfg) != set(defaults()):
        raise ValueError("Configuration keys differ from this release; review config.json against the example.")
    for key in ("read_only", "allow_send", "allow_calendar_invites", "chat_approvals", "reminders"):
        if type(cfg[key]) is not bool:
            raise ValueError(f"{key} must be a boolean.")
    for key in ("username", "email_address", "timezone", "public_url"):
        if not isinstance(cfg[key], str) or any(ord(c) < 32 for c in cfg[key]):
            raise ValueError(f"Invalid {key}.")
    if not cfg["username"] or "@" not in cfg["username"]:
        raise ValueError("An Apple Account email is required.")
    try:
        ZoneInfo(cfg["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Use a valid IANA timezone.") from None
    if type(cfg["port"]) is not int or not 1024 <= cfg["port"] <= 65535:
        raise ValueError("Choose an unprivileged port between 1024 and 65535.")
    if cfg["read_only"] and (cfg["allow_send"] or cfg["allow_calendar_invites"]):
        raise ValueError("Sending/invitations require --allow-writes.")
    if cfg["public_url"]:
        url = urlsplit(cfg["public_url"])
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("Invalid public HTTPS port.")
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Public URL must be an HTTPS base URL without credentials, query or fragment.")
        if "%" in url.path or ".." in url.path.split("/") or "//" in url.path:
            raise ValueError("Use a simple public URL path prefix.")
    return cfg


def private_dir(path: Path):
    if path.is_symlink():
        raise ValueError("Refusing a symlink at a managed directory.")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise ValueError("Managed directory must belong to the current user.")
    path.chmod(0o700)


def write_private(path: Path, data: bytes):
    # Exclusive temporary creation and replace prevent following a destination symlink.
    import tempfile
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix=".icloud-mcp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_config(root: Path) -> dict:
    path = root / "config.json"
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise ValueError("config.json must be owned by this user, private (0600), and not a symlink.")
    return validate(json.loads(path.read_text()))


def environment(cfg: dict, root: Path, inherited: dict | None = None) -> dict[str, str]:
    validate(cfg)
    inherited = os.environ if inherited is None else inherited
    # Do not inherit credentials, debug options or MCP settings from other installations.
    env = {k: v for k, v in inherited.items() if k in {"PATH", "HOME", "USER", "LOGNAME", "LANG", "TMPDIR"}}
    env.update(ICLOUD_USERNAME=cfg["username"], ICLOUD_EMAIL_ADDRESS=cfg["email_address"] or cfg["username"],
        ICLOUD_KEYCHAIN="true", ICLOUD_KEYCHAIN_SERVICE=APPLE_SERVICE,
        DATA_DIR=str(root / "data"), DEFAULT_TIMEZONE=cfg["timezone"],
        MCP_HOST="127.0.0.1", MCP_PORT=str(cfg["port"]), MCP_PUBLIC_URL=cfg["public_url"].rstrip("/"),
        READ_ONLY=str(cfg["read_only"]).lower(), ALLOW_SEND=str(cfg["allow_send"]).lower(),
        ALLOW_CALENDAR_INVITES=str(cfg["allow_calendar_invites"]).lower(),
        ALLOW_PERMANENT_DELETE="false", SEND_REQUIRES_APPROVAL=str(not cfg["chat_approvals"]).lower(),
        ENABLE_MAIL="true", ENABLE_CALENDAR="true", ENABLE_CONTACTS="true",
        ENABLE_EVENTKIT_REMINDERS=str(cfg["reminders"]).lower(), ENABLE_REMINDERS="false",
        ENABLE_NOTES="false", ENABLE_DRIVE="false", ENABLE_MAPS="false", ENABLE_IMESSAGE="false", ENABLE_HEALTH="false",
        ADMIN_PORT="0", EVENTKIT_REMINDERS_SOCKET=str(root / "data/eventkit/reminders.sock"),
        TOOLS="mail,calendar,contacts,icloud_get_time" + (",reminders" if cfg["reminders"] else ""))
    return env


def plist(root: Path, helper: bool) -> dict:
    label = HELPER_LABEL if helper else SERVER_LABEL
    argv = ([str(root / "apps/iCloud MCP Reminders.app/Contents/MacOS/ICloudMCPReminders"), "--background"] if helper else
            [str(root / ".venv/bin/python"), str(root / "manage.py"), "run"])
    return dict(Label=label, ProgramArguments=argv, RunAtLoad=True,
                KeepAlive={"SuccessfulExit": False}, ProcessType="Interactive", LimitLoadToSessionType="Aqua",
                StandardOutPath=str(root / "logs" / (label + ".log")),
                StandardErrorPath=str(root / "logs" / (label + ".error.log")),
                WorkingDirectory=str(root))


def require_installed(root: Path):
    if not (root / ".venv/bin/python").is_file():
        raise ValueError("Install this public edition first.")


def install(root: Path, reminders: bool):
    if root.exists() or root.is_symlink():
        raise ValueError("Destination already exists. Refusing to replace an existing installation; see docs/OPERATIONS.md.")
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11 or newer is required.")
    if not shutil.which("swiftc"):
        raise ValueError("Apple Command Line Tools (swiftc) are required.")
    if len(str(root / "data/eventkit/reminders.sock").encode()) >= 104:
        raise ValueError("Home path is too long for the EventKit socket; do not install until the layout is adapted.")
    private_dir(root)
    for name in ("bin", "data", "logs", "apps"):
        private_dir(root / name)
    # A failure leaves an inert partial directory for inspection; never erases another installation.
    subprocess.run([sys.executable, "-m", "venv", str(root / ".venv")], check=True)
    python = str(root / ".venv/bin/python")
    subprocess.run([python, "-m", "pip", "install", "-c", str(SOURCE / "constraints.txt"), str(SOURCE)], check=True)
    subprocess.run(["swiftc", str(SOURCE / "scripts/keychain.swift"), "-o", str(root / "bin/store-keychain")], check=True)
    shutil.copy2(SOURCE / "scripts/manage.py", root / "manage.py")
    if reminders:
        subprocess.run(["/bin/zsh", str(SOURCE / "mac-reminders/build-app.sh")], check=True)
        shutil.copytree(SOURCE / "mac-reminders/build/iCloud MCP Reminders.app", root / "apps/iCloud MCP Reminders.app")
    print("Installed public edition. No services started, permissions requested or credentials read.")
    print("Next: python3 scripts/manage.py configure" + (" --enable-reminders" if reminders else ""))


def password_twice(prompt: str, minimum: int) -> str:
    if not sys.stdin.isatty():
        raise ValueError("Credential setup requires an interactive Terminal.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            first = getpass.getpass(prompt)
            second = getpass.getpass("Repeat: ")
    except getpass.GetPassWarning:
        raise ValueError("Hidden input is unavailable; no password will be read with echo enabled.") from None
    if first != second or len(first) < minimum or not first.strip() or len(first.encode()) > 4096:
        raise ValueError("Passwords did not match or had an invalid length. Nothing was stored for this entry.")
    return first


def store_secret(root: Path, service: str, account: str, secret: str):
    subprocess.run([str(root / "bin/store-keychain"), service, account], input=secret.encode(), check=True)


def configure(root: Path, args):
    require_installed(root)
    cfg = defaults()
    if (root / "config.json").exists():
        raise ValueError("Already configured. Edit the non-secret config.json or use rotate-credentials; see docs/OPERATIONS.md.")
    cfg.update(username=input("Apple Account email: ").strip(),
        timezone=input("IANA timezone (for example Europe/Madrid): ").strip(),
        public_url=args.public_url.rstrip("/"), port=args.port,
        read_only=not args.allow_writes, allow_send=args.allow_send,
        allow_calendar_invites=args.allow_invites, chat_approvals=args.chat_approvals, reminders=args.enable_reminders)
    validate(cfg)
    if cfg["reminders"] and not (root / "apps/iCloud MCP Reminders.app").is_dir():
        raise ValueError("Helper was not installed. Do not enable Reminders yet.")
    apple = password_twice("Apple app-specific password (hidden): ", 16)
    owner = password_twice("Separate OAuth owner password (hidden, at least 12 characters): ", 12) if cfg["public_url"] else ""
    if owner and owner == apple:
        raise ValueError("Use a separate OAuth password.")
    store_secret(root, APPLE_SERVICE, cfg["username"], apple)
    if owner:
        store_secret(root, OWNER_SERVICE, cfg["username"], owner)
    write_private(root / "config.json", (json.dumps(cfg, indent=2) + "\n").encode())
    print("Saved private configuration and Keychain items. No account requests or services started.")


def run(root: Path, stdio: bool):
    require_installed(root)
    cfg = read_config(root)
    if not stdio and not cfg["public_url"]:
        raise ValueError("HTTP mode requires your own HTTPS public_url. See docs/REMOTE.md.")
    env = environment(cfg, root)
    if not stdio:
        r = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", OWNER_SERVICE,
                            "-a", cfg["username"], "-w"], capture_output=True)
        if r.returncode:
            raise ValueError("OAuth password is unavailable in the login Keychain. Unlock it or rotate credentials locally.")
        env["MCP_OWNER_PASSWORD"] = r.stdout.decode().rstrip("\r\n")
    python = str(root / ".venv/bin/python")
    os.execve(python, [python, "-m", "icloud_mcp", *(["--stdio"] if stdio else [])], env)


def start(root: Path, helper: bool):
    require_installed(root)
    cfg = read_config(root)
    if helper and (not cfg["reminders"] or not (root / "apps/iCloud MCP Reminders.app").is_dir()):
        raise ValueError("Reminders must be installed and explicitly enabled first.")
    if not helper and not cfg["public_url"]:
        raise ValueError("Configure HTTPS first, or use run --stdio without a server LaunchAgent.")
    item = plist(root, helper)
    destination = Path.home() / "Library/LaunchAgents" / (item["Label"] + ".plist")
    if destination.exists() or destination.is_symlink():
        raise ValueError("This public-edition agent already exists; use stop first, never overwrite another agent.")
    # Do not chmod the user's shared LaunchAgents directory.
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(plistlib.dumps(item))
    subprocess.run(["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(destination)], check=True)
    print("Started at login:", item["Label"])


def stop(helper: bool):
    label = HELPER_LABEL if helper else SERVER_LABEL
    destination = Path.home() / "Library/LaunchAgents" / (label + ".plist")
    if not destination.is_file() or destination.is_symlink():
        raise ValueError("No public-edition agent file found.")
    item = plistlib.loads(destination.read_bytes())
    if item.get("Label") != label or item.get("ProgramArguments") != plist(default_root(), helper)["ProgramArguments"]:
        raise ValueError("Agent definition differs; inspect manually before stopping it.")
    # bootout can report not loaded; remove persistence only after confirming it is no longer loaded.
    domain = f"gui/{os.getuid()}/{label}"
    subprocess.run(["/bin/launchctl", "bootout", domain], capture_output=True)
    if subprocess.run(["/bin/launchctl", "print", domain], capture_output=True).returncode == 0:
        raise ValueError("Agent is still loaded. Persistence file retained.")
    destination.unlink()
    print("Stopped only this public-edition agent; data and credentials retained.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    i = sub.add_parser("install"); i.add_argument("--enable-reminders", action="store_true")
    c = sub.add_parser("configure")
    for flag in ("allow-writes", "allow-send", "allow-invites", "chat-approvals", "enable-reminders"):
        c.add_argument("--" + flag, action="store_true")
    c.add_argument("--public-url", default=""); c.add_argument("--port", type=int, default=8876)
    r = sub.add_parser("run"); r.add_argument("--stdio", action="store_true")
    for command in ("start", "stop"):
        s = sub.add_parser(command); s.add_argument("--helper", action="store_true")
    sub.add_parser("open-reminders")
    sub.add_parser("rotate-credentials")
    sub.add_parser("client-config")
    args = p.parse_args(argv)
    if sys.platform != "darwin" or int(platform.mac_ver()[0].split(".")[0] or 0) < 14:
        p.error("The public installer requires macOS 14 or later. No changes made.")
    os.umask(0o077)
    root = default_root()
    try:
        if args.command == "install": install(root, args.enable_reminders)
        elif args.command == "configure": configure(root, args)
        elif args.command == "run": run(root, args.stdio)
        elif args.command == "start": start(root, args.helper)
        elif args.command == "stop": stop(args.helper)
        elif args.command == "open-reminders":
            require_installed(root)
            if not read_config(root)["reminders"]: raise ValueError("Reminders are not enabled.")
            subprocess.run(["/usr/bin/open", str(root / "apps/iCloud MCP Reminders.app")], check=True)
        elif args.command == "rotate-credentials":
            require_installed(root); cfg = read_config(root)
            apple = password_twice("New Apple app-specific password: ", 16)
            owner = password_twice("New separate OAuth password: ", 12) if cfg["public_url"] else ""
            if owner and owner == apple: raise ValueError("Use separate passwords.")
            store_secret(root, APPLE_SERVICE, cfg["username"], apple)
            if owner: store_secret(root, OWNER_SERVICE, cfg["username"], owner)
            print("Keychain updated. Restart public services/stdio clients to use the new credentials.")
        else:
            require_installed(root)
            print(json.dumps({"mcpServers": {"icloud-mcp-macos": {"command": str(root / ".venv/bin/python"),
                "args": [str(root / "manage.py"), "run", "--stdio"]}}}, indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        # Never echo subprocess argv/stdout/stderr or credential input.
        message = str(e) if isinstance(e, ValueError) else "Local operation failed; inspect the preceding step without sharing secrets."
        p.exit(1, message + "\n")

if __name__ == "__main__":
    main()
