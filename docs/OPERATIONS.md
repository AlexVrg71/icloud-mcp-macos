# Operating the public edition

## Files and secrets

All state for this edition lives under `~/Library/Application Support/iCloud-MCP-macOS`:

- `.venv/`, `manage.py`, `bin/`, `apps/`: installed software.
- `config.json`: private configuration, mode 0600, containing the account, time zone, URL, port, and policies; never passwords. Refer to the structure of `defaults()` when comparing it. Do not add arbitrary variables.
- `data/`: OAuth tokens, operation receipts, vCard backups, calendar recovery data, and temporary attachments. It may contain complete personal records. Do not upload it to GitHub.
- `data/eventkit/`: a mode-0600 socket, list identification, and durable mutation receipts. Do not delete pending receipts to force a retry.
- `logs/`: private diagnostics; review before sharing.

Keychain uses the services `icloud-mcp-macos.apple` and `icloud-mcp-macos.oauth` with the configured account. These are generic Keychain items, viewable in Keychain Access. They are not website credentials stored in the Passwords app. The native utility receives the secret through stdin and saves it using Security.framework, without putting it in command-line arguments or temporary files. The launcher retrieves the OAuth password without printing it and passes it in the server's process environment. The server reads the Apple password from Keychain. This does not protect against malware running with the owner's privileges.

`python3 scripts/manage.py rotate-credentials` prompts for replacements in Terminal. It does not create or revoke Apple passwords: manage those in your Apple Account. To add HTTP to a stdio-only configuration, stop the server, add your `public_url` to `config.json`, run `rotate-credentials` to save the OAuth password as well, then restart. Changing the owner password alone does not invalidate all previously issued OAuth tokens.

To revoke sessions, stop the server and privately remove `data/oauth_state.json` (this discards saved clients/tokens); clients must reconnect after startup. Verify the file first and preserve a backup if you need to investigate an incident. Do not copy tokens into issues.

## Starting and stopping

```sh
python3 scripts/manage.py start --helper  # enable EventKit helper at login
python3 scripts/manage.py start           # enable HTTP server at login
python3 scripts/manage.py stop            # stop and remove only this edition's HTTP agent
python3 scripts/manage.py stop --helper   # stop and remove only this edition's EventKit agent
```

Labels: `org.icloudmcp.macos.server` and `org.icloudmcp.macos.reminders`. With stdio, your client manages the server; do not run HTTP `start`. Use only one write-enabled server process for this edition to avoid races involving receipts and backups; multiple remote connections to that server are expected. The helper prevents two processes from opening the same socket.

The scripts refuse to replace existing destinations or agents. A failed installation may leave a partial directory without services; inspect it before moving or removing it. A bootstrap failure may leave a LaunchAgent file; `stop` can remove it after verifying it is not loaded. There is no automatic deletion of data or Keychain items.

## Policies and configuration changes

`read_only=true` omits write tools. To enable writes in a configured installation, stop the server/clients, set that boolean to `false`, then restart and refresh the catalog. `allow_send`, `allow_calendar_invites`, and `chat_approvals` are independent options. Keep change approval enabled in the client; `chat_approvals=true` only removes the second mail approval page and does not authenticate each user instruction.

Legacy options absent from `config.json` are not inherited from the shell environment. The launcher disables broader helpers and the administration API. Do not add passwords to `config.json` or enable overrides that store secrets on disk.

## Updating and removal

This beta **has no automatic updater**. Do not replace an active installation while it is running. Retain the previous source/version and a private directory backup, stop clients and both agents, and prepare the next version separately. The installer does not migrate previous installations; an update needs reviewed migration instructions. Replacing an ad hoc signed app may require granting Reminders access again. Do not reset TCC or disable Gatekeeper to bypass this.

To remove this edition, first stop stdio clients and run both `stop` commands. Revoke Reminders permission in System Settings if desired. Then manually remove this edition's app, data, and Keychain entries after deciding which backups to retain. Do not remove other services' agents or paths.

## Retention and recovery

Contact backups, calendar split manifests, and Reminders receipts have no automatic cleanup. They can grow and contain private data. Keep encrypted backups and define a manual retention policy. Deleting receipts removes protection against old retries. Restoring a backup requires review; there is no universal automatic restore.

After an uncertain result, read or search first. Do not repeat a creation with another `request_id`; retain the original UUID and arguments. A recurring CalDAV change can involve two resources: splitting is not atomic, so inspect both before resolving the result.
