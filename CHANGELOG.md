# Changelog

## Documentation update — 2026-11-01

- Separate local and remote onboarding before initial configuration.
- Add a dedicated-host Tailscale Funnel walkthrough, OAuth checks, client setup, and existing-install migration.
- Document first-connection validation, troubleshooting, and current native iCloud plugin capabilities without claiming unperformed live tests.

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
