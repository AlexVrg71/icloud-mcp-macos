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

## Choose your connection before configuring

| Where you will use it | Connection | Continue with |
| --- | --- | --- |
| Claude Desktop on this Mac | Local stdio; no public endpoint or OAuth | [Local setup](#local-setup-claude-desktop) |
| ChatGPT, or Claude through a remote connector | HTTPS + OAuth to this Mac | [Remote setup](docs/REMOTE.md) |

**Choose one route. Run `install` once and `configure` once.** The local and remote commands are alternatives, not consecutive steps. Already configured? Use [switching from local to remote](docs/REMOTE.md#switching-an-existing-local-installation-to-remote); rerunning `configure` deliberately fails.

Before installing, check that your client/account lets you add a custom MCP server. Workspace policies can restrict access. GitHub publication does not automatically list or install this connector in ChatGPT or Claude.

If you only need iCloud Mail and Calendar in ChatGPT, consider OpenAI's built-in plugins first. This project's additional reasons to self-host include EventKit Reminders, contact editing with backups, and a portable MCP endpoint. See the [dated feature comparison](docs/NATIVE-ICLOUD-COMPARISON.md).

## Prepare the Mac — both routes

1. Confirm macOS 14+ and check the tools in Terminal:

   ```sh
   sw_vers -productVersion
   python3 --version
   swift --version
   git --version
   ```

   Python must be 3.11+. Install a suitable Python from [python.org](https://www.python.org/downloads/macos/) if needed. Install Apple's Command Line Tools with `xcode-select --install` if Swift/Git are missing, then reopen Terminal and repeat the checks. Do not use `sudo` for this project's commands.

2. Enable the iCloud services you intend to use. For Reminders, sign into iCloud on this Mac, enable Reminders synchronization, and confirm your iCloud lists appear in Apple's Reminders app. A local list is not an iCloud list.

3. Generate an app-specific password in [Apple Account → Sign-In and Security → App-Specific Passwords](https://support.apple.com/en-us/102654). Apple requires two-factor authentication. Keep this password outside chat and use it only in the hidden Terminal prompt. The remote route also asks you to create a **different OAuth owner password**, at least 12 characters long.

4. Clone the source and review it:

   ```sh
   git clone https://github.com/AlexVrg71/icloud-mcp-macos.git
   cd icloud-mcp-macos
   python3 scripts/manage.py install --enable-reminders
   ```

   This creates a separate Python environment, installs dependencies with `constraints.txt`, and compiles the helper. It does not start services or request permissions. To omit Reminders, omit `--enable-reminders` from both `install` and your chosen `configure` command, and skip helper steps throughout the guide.

Keep Terminal in the cloned directory for subsequent commands. If installation reports an existing destination, inspect it using [operations guidance](docs/OPERATIONS.md); do not delete a working installation to retry.

## Local setup: Claude Desktop

After the preparation above, configure local access:

```sh
python3 scripts/manage.py configure --enable-reminders
```

Enter the Apple Account, an IANA time zone such as `America/Mexico_City`, and the app-specific password twice with hidden input. This starts in **read-only mode**. To enable changes during initial configuration, add `--allow-writes`; sending mail and invitations separately require `--allow-send` and `--allow-invites`. Decide before executing the command; later changes use [configuration policies](docs/OPERATIONS.md#policies-and-configuration-changes).

Secrets are generic Keychain items, viewable in Keychain Access; they may not appear in the Passwords app. Approve macOS Keychain access only for the installed program you intended to run.

If Reminders is enabled, complete [Reminders permissions](#reminders-permissions) below. Then generate the local client configuration:

```sh
python3 scripts/manage.py client-config
```

In Claude Desktop's macOS menu, open **Settings → Developer → Edit Config**. Merge the generated `icloud-mcp-macos` entry into `mcpServers` in `~/Library/Application Support/Claude/claude_desktop_config.json`. Preserve existing entries and other settings; do not paste a second top-level JSON object. Use the generated absolute paths, not `~` placeholders. Fully quit and reopen Claude Desktop, then check that this server's tools appear. See the [official local MCP guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers) if the UI has changed.

Claude launches the stdio server; **do not run `start` for the HTTP server on this route**. This local configuration is separate from Claude's account-level remote connectors. It is not a ChatGPT import file. It contains local paths but no passwords; do not publish it. Start with [read-only validation](#first-connection-validation).

## Reminders permissions

Only if you installed and configured Reminders, run:

```sh
python3 scripts/manage.py start --helper
python3 scripts/manage.py open-reminders
```

`start --helper` enables this helper at login. Do not repeat it if already running. In the local window:

1. Click **Request Reminders Access…**, review the explanation, and grant access in macOS.
2. Click **Refresh Lists**, select an iCloud list, check **I confirm this list belongs to my iCloud account**, choose its sharing status, and click **Save List Identification**.
3. Repeat for each list you want writable. No reminder needs to be created.

Apple grants access to all Reminders lists; the helper limits writes to those you identify as iCloud. Classification and sharing labels are owner declarations, not automatically verified by EventKit. If permission was denied, review **System Settings → Privacy & Security → Reminders**. Do not reset system privacy controls. Server read-only mode still blocks writes even after a list is enabled.

## First connection validation

Select this connector explicitly and ask:

> Use iCloud MCP for macOS to run icloud_check_health. List mail folders, calendars, and Reminders lists, and check Reminders permission. Do not create, send, edit, mark, or delete anything.

Check that enabled areas report success, the expected account/lists are present, and Reminders reports access if enabled. Reading real data requires your own connected account; synthetic tests alone do not establish this result. A successful connection with no write tools is expected in read-only mode.

For write access, follow [configuration policies](docs/OPERATIONS.md#policies-and-configuration-changes), restart the relevant process, refresh the client's tools, and keep write approval enabled. Only test a write after explicitly authorizing a specific disposable object. Read it back and separately authorize cleanup. Creating a reminder locally, seeing it on iPhone/Watch, and receiving its alert are three distinct checks.

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
