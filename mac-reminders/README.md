# iCloud MCP Reminders: EventKit

macOS 14+, SwiftPM 5.9+, no external Swift dependencies. Products: the `ICloudMCPReminders` executable, the `RemindersCore` library, and its tests.

```sh
swift test
./build-app.sh
```

The built app is at `build/iCloud MCP Reminders.app`. It is an ad hoc signed development build with identity `org.icloudmcp.macos.reminders`, without notarization; building does not launch it. The executable's `--self-check` checks only the protocol without creating an EKEventStore, requesting permission, or opening a socket. Do not run the live app during CI.

The process is integrated through the installer in the [main README](../README.md). Data: `~/Library/Application Support/iCloud-MCP-macOS/data/eventkit`. It uses a private socket, same-UID access, MainActor, serialized requests, and durable receipts. See [architecture](../docs/ARCHITECTURE.md) and [security](../SECURITY.md).

Tools:

| Name | Purpose |
| --- | --- |
| `reminders_get_status` | Check connection and permission without requesting access. |
| `reminders_list_lists` | Read list/account identity, classification, declared sharing, and write access. |
| `reminders_list_reminders` | Search pending/completed reminders with explicit pagination. |
| `reminders_get_reminder` | Read one item and its version. |
| `reminders_create_reminder` | Require an explicit list, UUID, confirmation, title, and explicit alert choice. |
| `reminders_update_reminder` | Apply specific changes with a version; date changes require an alert choice. |
| `reminders_complete_reminder` | Set completed/pending state rather than blindly toggling it. |
| `reminders_delete_reminder` | Delete exactly one item with an explicit instruction and version. |

Timed dates require an IANA time zone. Ambiguous or nonexistent times caused by clock changes are rejected. A date without a time does not imply an alert. Recurrences, lists, subtasks, tags, and attachments cannot be modified.

Privacy controls are local and declared by the owner; an account named “iCloud” must not be described as verified without that confirmation. The helper can read what EventKit exposes but can write only to lists confirmed as iCloud. Unknown/shared/delegated lists require permission acknowledging collaborator visibility. Never grant TCC permission from an MCP tool.

`local_saved` does not prove synchronization or notification delivery. The server leaves `sync_status`, `iphone_notification`, and `watch_notification` as `not_verified`; human confirmation on devices is documented separately.
