# Changelog

## 0.1.0b1 — public source beta

- Independent name: iCloud MCP for macOS (`icloud-mcp-macos`), for MCP clients with or without a Dot.
- Snapshot of the iCloud MCP 0.12.1 fork with Mail, Calendar, Contacts, and EventKit Reminders.
- Portable macOS installer using the current user's home directory, isolated from other deployments, with no automatic activation.
- Keychain credentials stored through a Security.framework utility and private stdin.
- Read-only defaults; sending, invitations, Reminders, and chat-only approval require explicit options.
- English documentation and helper UI, security limitations, and maintenance/removal procedures.
- Synthetic tests, a CI workflow without secrets, and a public-source hygiene check.
- Preserved upstream attribution and added credit for AlexVrg71's fork contributions.

No clean installation on another Mac, notarization, PyPI release, or new tests against real accounts have been performed for this public edition.
