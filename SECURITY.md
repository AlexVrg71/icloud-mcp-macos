# iCloud MCP for macOS security

## Scope of this beta

Each deployment serves one owner. An authorized MCP client can read sensitive information and, when writes are enabled, modify it. This is not a multi-user service. Emails, invitations, notes, and list names are untrusted data and may contain malicious instructions.

- The public installer defaults to read-only mode, without sending, invitations, administration ports, or broader helpers.
- HTTP uses OAuth, an owner password, PKCE, and redirect validation; the internal port listens on loopback. The operator is responsible for the HTTPS proxy.
- Stdio trusts the local client and operating-system session. It does not use OAuth.
- Passwords are stored in Keychain, not in the repository or `config.json`. OAuth needs its password in process memory/environment at startup. This does not protect against a malicious process running under the same macOS account.
- The EventKit helper uses a private Unix socket, checks the peer UID, and accepts a fixed set of operations. It does not execute commands received through MCP.
- TCC permission is requested only through the local UI. Apple's authorization covers all lists; per-list write restrictions are enforced by the helper.
- Receipts and backups contain private information. Files use mode 0600 within 0700 directories. There is no automatic retention policy; do not upload them to GitHub.

## Approval and writes

`READ_ONLY=true` blocks writes. `ALLOW_SEND=false` blocks mail sends. `ALLOW_CALENDAR_INVITES=false` blocks invitations. The launcher disables permanent mail deletion. Permission to read does not authorize changes requested by the content being read.

`confirmed=true` and MCP annotations support approval-aware clients; they are not cryptographic proof of human approval. For independent mail approval, keep `SEND_REQUIRES_APPROVAL=true` with HTTP. `chat_approvals=true` removes that page and trusts the authorized client. Calendar, Contacts, and Reminders have no separate approval page: use a trusted client with write confirmations, or stay in read-only mode.

Deleting a reminder requires an exact item identity and an explicit instruction. The connector does not provide undo. Writes require a stable UUID; do not create another UUID to bypass protection after an uncertain result. Versions are compared against the local replica and do not provide atomic edits across devices.

The iCloud and sharing classifications of lists rely on the owner's local confirmation; EventKit cannot verify all providers or sharing arrangements. Shared, delegated, or unknown lists require acknowledgment of collaborator visibility. Do not enable a list without understanding who can see its data.

## Data leaving the server

- Mail and invitations go to the selected recipients when enabled, subject to the approvals described above.
- Members of shared lists, calendars, or contact resources may see changes. EventKit's detailed privacy controls do not apply to every CalDAV/CardDAV resource.
- Temporary attachment download links grant access by possession; do not publish them or log them in full.
- The MCP client receives the data it requests. A local server does not imply that the client or its model also runs locally.

## Reporting vulnerabilities

Do not post credentials, account data, tokens, download links, or personal content in issues. **Private vulnerability reporting** is enabled. Use [Report a vulnerability](https://github.com/AlexVrg71/icloud-mcp-macos/security/advisories/new) to send a private report to this repository's maintainers. Do not open a public issue with sensitive details or report fork-specific defects to upstream.

Include the version, sanitized configuration, reproduction using synthetic data, and impact. No response-time commitment or external audit is promised. Release review and automated tests are not a comprehensive security audit.
