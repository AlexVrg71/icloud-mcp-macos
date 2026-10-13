import Foundation
import EventKit
import RemindersCore

@MainActor
final class ReminderStore {
    let store = EKEventStore()
    let root: URL
    let journal: Journal
    init(root: URL) throws { self.root = root; journal = try Journal(directory: root.appendingPathComponent("journal")) }
    var authorization: String {
        switch EKEventStore.authorizationStatus(for: .reminder) {
        case .notDetermined: return "not_determined"
        case .restricted: return "restricted"
        case .denied: return "denied"
        case .fullAccess: return "full_access"
        case .writeOnly: return "write_only_insufficient"
        @unknown default: return "unknown"
        }
    }
    func requireAccess() throws {
        guard authorization == "full_access" else { throw Failure("permission_\(authorization)", "Open iCloud MCP Reminders on the Mac and grant Reminders access only with the owner's authorization. No remote tool can request permission.") }
    }
    func bindings() -> [String: [String: String]] {
        guard let data = try? Data(contentsOf: root.appendingPathComponent("lists.json")),
              let obj = try? JSONDecoder().decode([String: [String: String]].self, from: data) else { return [:] }
        return obj
    }
    func listInfo(_ c: EKCalendar) -> [String: Any] {
        var info = ListPolicy.classify(local: c.source.sourceType == .local, delegated: c.source.isDelegate,
            sourceID: c.source.sourceIdentifier, name: c.source.title, binding: bindings()[c.calendarIdentifier])
        info.merge(["id": c.calendarIdentifier, "name": c.title, "source_id": c.source.sourceIdentifier,
            "source_name": c.source.title, "source_type": c.source.sourceType.rawValue,
            "writable": c.allowsContentModifications, "subscribed": c.isSubscribed]) { _, new in new }
        return info
    }
    func resolve(_ r: Request) throws -> [EKCalendar] {
        try ListPolicy.select(store.calendars(for: .reminder), id: r.list_id, name: r.list_name,
                              getID: { $0.calendarIdentifier }, getName: { $0.title })
    }
    func writable(_ c: EKCalendar, _ r: Request) throws {
        try ListPolicy.requireWrite(listInfo(c), writable: c.allowsContentModifications, allowShared: r.allow_shared == true)
    }
    func record(_ r: EKReminder) throws -> [String: Any] {
        var out: [String: Any] = ["id": r.calendarItemIdentifier, "title": r.title ?? "", "notes": r.notes ?? "",
            "list": listInfo(r.calendar), "completed": r.isCompleted, "recurring": r.hasRecurrenceRules,
            "modified_at": r.lastModifiedDate.map(iso) ?? "", "completed_at": r.completionDate.map(iso) ?? "",
            "sync_status": "not_verified", "iphone_notification": "not_verified", "watch_notification": "not_verified"]
        if let c = r.dueDateComponents {
            out["due_date"] = String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
            if let hour = c.hour { out["due_time"] = String(format: "%02d:%02d", hour, c.minute ?? 0) }
            out["timezone"] = c.timeZone?.identifier ?? r.timeZone?.identifier ?? "floating_or_unknown"
        }
        out["alarms"] = (r.alarms ?? []).map { a -> [String: Any] in
            var item: [String: Any] = ["relative_seconds": a.relativeOffset, "location_based": a.structuredLocation != nil]
            if let date = a.absoluteDate { item["at"] = iso(date) }; return item
        }
        out["version"] = digest(try canonical(out))
        return out
    }
    func iso(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }
    func lookup(_ id: String) throws -> EKReminder {
        guard let r = store.calendarItem(withIdentifier: id) as? EKReminder else { throw Failure("reminder_not_found", "Reminder id is stale, removed or unavailable. Search again; never silently recreate it.") }
        return r
    }
    func fetch(_ lists: [EKCalendar]) async throws -> [EKReminder] {
        if lists.isEmpty { return [] }
        return try await withCheckedThrowingContinuation { continuation in
            store.fetchReminders(matching: store.predicateForReminders(in: lists)) { result in
                guard let result else { continuation.resume(throwing: Failure("fetch_failed", "EventKit returned no result; this is not proof that the list is empty.")); return }
                continuation.resume(returning: result)
            }
        }
    }
    func execute(_ r: Request) async throws -> [String: Any] {
        try r.validate()
        if r.op == "status" {
            // No access request or data fetch as a side effect of diagnosis.
            return ["ok": authorization == "full_access", "online": true, "authorization": authorization,
                    "backend": "EventKit", "version": "1.0.0", "configured_icloud_lists": bindings().count,
                    "sync_status": "not_verified", "iphone_notification": "not_verified", "watch_notification": "not_verified"]
        }
        try requireAccess(); store.reset()
        if r.op == "lists" { return ["lists": store.calendars(for: .reminder).map(listInfo), "sharing_notice": "EventKit does not expose a reliable shared/private flag for every list; unknown is never private.", "sync_status": "not_verified"] }
        if r.op == "search" {
            var found = try await fetch(resolve(r))
            let mode = r.completed ?? "pending"
            found = found.filter { (mode == "all" || $0.isCompleted == (mode == "completed")) && (r.query == nil || (($0.title ?? "") + "\n" + ($0.notes ?? "")).localizedCaseInsensitiveContains(r.query!)) }
            found.sort { $0.calendarItemIdentifier < $1.calendarItemIdentifier }
            let page = Array(found.dropFirst(r.offset ?? 0).prefix(r.limit ?? 50))
            let next = (r.offset ?? 0) + page.count
            return ["reminders": try page.map(record), "count": page.count, "total": found.count, "complete": next >= found.count,
                    "next_offset": next < found.count ? next as Any : NSNull(), "pagination_notice": "Live snapshot; concurrent edits can change later pages."]
        }
        if r.op == "read" { return ["reminder": try record(lookup(r.id!))] }
        var reminder: EKReminder!
        var target: EKCalendar!
        var alarmDate: Date?
        let plan = try DuePlan(request: r)
        return try journal.perform(r, validate: {
            if r.op == "create" {
                target = try self.resolve(r).first!
                try self.writable(target, r)
                reminder = EKReminder(eventStore: self.store); reminder.calendar = target
            } else {
                reminder = try self.lookup(r.id!)
                guard try self.record(reminder)["version"] as? String == r.expected_version else { throw Failure("conflict", "The reminder changed. Read it and obtain approval for the current version before retrying.") }
                try self.writable(reminder.calendar, r)
                guard !reminder.hasRecurrenceRules else { throw Failure("recurrence_not_supported", "Mutating recurring reminders is not supported in this release; use Apple Reminders.") }
                if let _ = r.list_id {
                    target = try self.resolve(r).first!
                    try self.writable(target, r)
                    guard target.source.sourceIdentifier == reminder.calendar.source.sourceIdentifier else { throw Failure("cross_account_move", "Cannot move between accounts.") }
                }
            }
            if r.alarm == "at_due" || r.alarm == "before_due" {
                var base = plan.instant
                if r.due_date == nil, let c = reminder.dueDateComponents, c.hour != nil, let zone = c.timeZone ?? reminder.timeZone {
                    var cal = Calendar(identifier: .gregorian); cal.timeZone = zone; base = cal.date(from: c)
                }
                guard let base else { throw Failure("invalid_alarm", "A timed alarm needs a date, time and explicit timezone.") }
                alarmDate = base.addingTimeInterval(-Double(r.minutes_before ?? 0) * 60)
            }
            if r.op == "update", r.due_date != nil, r.alarm == nil { throw Failure("alarm_choice_required", "When changing the date/time explicitly choose none, at_due or before_due to avoid retaining an old alarm time.") }
        }, save: {
            if r.op == "delete" {
                let before = try self.record(reminder!)
                try self.store.remove(reminder!, commit: true)
                return ["deleted": true, "id": r.id!, "title": before["title"]!, "local_saved": true, "sync_status": "not_verified"]
            }
            if let title = r.title { reminder.title = title }
            if let notes = r.notes { reminder.notes = notes }
            if let target { reminder.calendar = target }
            if r.clear_due == true { reminder.dueDateComponents = nil; reminder.startDateComponents = nil; reminder.alarms = nil }
            else if let components = plan.components { reminder.dueDateComponents = components; reminder.timeZone = components.timeZone }
            if let _ = r.alarm { reminder.alarms = alarmDate.map { [EKAlarm(absoluteDate: $0)] } ?? [] }
            if r.op == "complete" { reminder.isCompleted = r.completed == "completed" }
            try self.store.save(reminder, commit: true)
            return ["reminder": try self.record(reminder), "local_saved": true, "sync_status": "not_verified",
                    "iphone_notification": "not_verified", "watch_notification": "not_verified"]
        })
    }
}
