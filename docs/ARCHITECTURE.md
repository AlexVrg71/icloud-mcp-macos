# Architecture

```text
Local MCP client ── stdio ────────────────┐
Remote client ── HTTPS + OAuth ── proxy ──┤
                                        └── Python server
                                            ├── IMAP/SMTP: iCloud Mail
                                            ├── CalDAV: calendars
                                            ├── CardDAV: contacts + backups
                                            └── private Unix socket ── Swift/EventKit app
                                                                        └── macOS Reminders replica
```

The repository retains the Python package `icloud_mcp` and uses the separate distribution name `icloud-mcp-macos`. Its independent launcher builds the environment from explicit configuration, avoiding inherited secrets, paths, or features from another installation.

The helper uses SwiftPM: the pure `RemindersCore` library, the `ICloudMCPReminders` executable, and `RemindersCoreTests`. `build-app.sh` creates the AppKit bundle, declares the permission purpose, and signs it ad hoc. The app is not opened during builds or tests. The `scripts/keychain.swift` utility stores credentials only in this edition's two Keychain services using Security.framework; it is compiled separately and does not request EventKit access.

The public identity is `org.icloudmcp.macos.reminders`; data lives at `~/Library/Application Support/iCloud-MCP-macOS/data/eventkit`. The server and helper derive this shared path from the user's home directory. The socket path is subject to the macOS Unix socket limit; the installer rejects overly long paths. It does not change permissions on another installation's directories.

EventKit runs on MainActor. IPC serializes reads and mutations. A lock file excludes a second helper; requests have a bounded size and the server times out without automatic retries. The operation journal records pending state before writing and the result afterward. A failure between those steps leaves an uncertain result that requires manual reconciliation.

Permissions are not granted remotely or on startup. The user selects lists in the app and saves their account/list identifiers; changed identifiers require a new selection. Apple synchronization and notification delivery are separate from confirmation of a local save.

Changes from upstream include OAuth prefix handling, vCard backups, threads across folders, temporary attachments, recurrence splitting with recovery, and deduplicated iMIP replies. The remaining core is retained to avoid unrelated refactoring during publication.
