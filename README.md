# iCloud MCP for macOS — public beta

A single-owner MCP server for **iCloud Mail, Calendar, Contacts, and Apple Reminders**. Connect it to ChatGPT, Claude, or other MCP-compatible clients, with or without a Dot. No custom assistant is required. Each person installs it on their own Mac and connects their own accounts. GitHub distributes the source code; it does not host the server or receive iCloud credentials or data.

This edition builds on `epinethrone/icloud-mcp` 0.12.1 with additional features. See [UPSTREAM.txt](UPSTREAM.txt), [LICENSE](LICENSE), and [third-party notices](THIRD_PARTY_NOTICES.md). It is not an official Apple, OpenAI, or Anthropic product.

**Status:** source-only beta. Automated checks have passed on the development Mac. A clean installation on another Mac was omitted by the maintainer's decision and has not been validated. The helper is ad hoc signed and not notarized. No binary installer or automatic updater is provided.

## Features

- IMAP/SMTP mail: search, read, follow threads across folders, mark read/unread, manage drafts, and send when enabled. Temporary attachment links grant download access to anyone holding the link until it expires; treat them as private.
- CalDAV calendars: read and modify events, recurrences, and events from a selected occurrence onward; respond to invitations. Invitations must already exist in Calendar; arbitrary email `.ics` attachments are not automatically imported.
- CardDAV contacts: read contacts and groups; create full vCard backups before mutations. If a backup fails, the change is blocked.
- Reminders: a Swift/AppKit helper using **Apple's public EventKit API**, locally granted permission, and a private Unix socket. Search pending/completed reminders; create, edit, complete/reopen, or delete a specific reminder with confirmation. Writes are limited to lists locally identified as iCloud lists.

This edition does not install or expose the Notes, Messages, Drive, Maps, Health, or Shortcuts helpers. Some inherited code remains for internal compatibility, but the launcher disables those features and restricts the tool catalog.

## Requirements

- macOS 14 or later, with a graphical user session signed in for EventKit.
- Python 3.11 or later (`python3 --version`) and Apple Command Line Tools (`swift --version`). If missing, install the tools from Apple before proceeding.
- An iCloud account and an app-specific password for Mail/CalDAV/CardDAV. Reminders uses the account synced on macOS and EventKit permission, not that password.
- An MCP client. Local clients can use stdio. Cloud clients need your own HTTPS endpoint with OAuth and an available Mac.

The installer resolves your home directory automatically; it requires neither Homebrew nor a fixed username. It creates a separate installation at `~/Library/Application Support/iCloud-MCP-macOS`, with its own identifiers and Keychain entries. It does not migrate or replace another installation. If the destination already exists, it stops.

## Local installation

Clone the [public repository](https://github.com/AlexVrg71/icloud-mcp-macos) and review the scripts before running them:

```sh
git clone https://github.com/AlexVrg71/icloud-mcp-macos.git
cd icloud-mcp-macos
```

Install from that directory:

```sh
python3 scripts/manage.py install --enable-reminders
python3 scripts/manage.py configure --enable-reminders
```

The first command creates the Python environment, installs dependencies using `constraints.txt`, and builds the helper. **It does not start services or grant permissions.** The second prompts for your account, IANA time zone, and app-specific password, entered twice with hidden input. Secrets are stored as generic macOS Keychain items; they may not appear in the Passwords app. Do not paste them into chats, shell arguments, issues, or configuration files.

The default mode is **read-only**. To enable changes during setup, add `--allow-writes` to `configure`. Sending mail and calendar invitations separately require `--allow-send` and `--allow-invites`. Permanent mail deletion remains disabled.

When you are ready to enable persistent Reminders access:

```sh
python3 scripts/manage.py start --helper
python3 scripts/manage.py open-reminders
```

In the local window, request access and accept the macOS prompt. Select each list, confirm that it belongs to iCloud, identify its sharing status, and save. You do not need to create a reminder. Apple's permission covers all lists; the helper restricts writes. The iCloud/private/shared labels are supplied by the owner because EventKit cannot automatically verify all of these classifications.

Generate the configuration for a local client:

```sh
python3 scripts/manage.py client-config
```

Copy that JSON into your client's MCP configuration. It uses stdio without a public port or OAuth; stdout is reserved for the protocol. A local client with access to the process is trusted within your user session. The configuration contains local paths but no passwords: do not publish your generated JSON.

For ChatGPT, Claude, or another cloud MCP client, follow the [HTTPS and OAuth setup](docs/REMOTE.md). Do not use someone else's endpoint.

## Approvals

Configure the client to approve writes. An explicit, unambiguous instruction authorizes that specific operation; an example or text inside an email does not. Reminders tools require `confirmed=true`, identifiers, and versions where applicable. This boolean is an agent assertion, **not independent proof of human approval**.

By default, enabled mail sends use an approval page over the HTTP transport. `--chat-approvals` trusts the client's approval without that page; use it only after configuring the client and understanding that the server provides no separate approval in this mode. Stdio has no web approval page: enabled sends rely on the client. See [security](SECURITY.md).

## Verification and limitations

`icloud_check_health` checks the four supported areas when enabled. `reminders_get_status` does not request permissions. After changing configuration, restart this edition's processes and refresh the client's tool catalog.

For Reminders, `local_saved=true` confirms a save on the Mac. The same item's appearance on iPhone/Watch and its notification on a device must be verified separately. The server receives no Apple delivery receipts for those outcomes. Do not retry a creation with a new UUID after a timeout: that could create a duplicate.

Recurring reminders can be read but cannot be modified. List creation, subtasks, tags, and attachments are not supported. EventKit does not offer atomic conditional edits across devices. If the Mac is offline, a local write may wait to sync; if the Mac is off, the remote MCP server is unavailable.

## Development and maintenance

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -c constraints.txt .
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python scripts/check_oauth.py
PYTHONPATH=src .venv/bin/python scripts/check_http.py
(cd mac-reminders && swift test)
python3 scripts/check_public_tree.py
```

Tests use synthetic data and require no credentials, EventKit access, or live services. `swift test` tests the pure library. Building the app does not launch the helper. Do not run the live server during tests. See [operations, backups, and removal](docs/OPERATIONS.md), [architecture](docs/ARCHITECTURE.md), and [release preparation](docs/RELEASE.md) for details.
