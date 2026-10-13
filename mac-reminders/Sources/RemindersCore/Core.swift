import Foundation
import CryptoKit
import Darwin

public struct Failure: Error, LocalizedError {
    public let code: String
    public let message: String
    public var errorDescription: String? { "\(code): \(message)" }
    public init(_ code: String, _ message: String) { self.code = code; self.message = message }
}

// Same narrow allowlist at both IPC boundaries; no executable script or path arguments.
public struct Request: Codable {
    public var op: String
    public var request_id: String?
    public var id: String?
    public var list_id: String?
    public var list_name: String?
    public var query: String?
    public var completed: String?
    public var limit: Int?
    public var offset: Int?
    public var title: String?
    public var notes: String?
    public var due_date: String?
    public var due_time: String?
    public var timezone: String?
    public var clear_due: Bool?
    public var alarm: String?
    public var minutes_before: Int?
    public var expected_version: String?
    public var confirmed: Bool?
    public var allow_shared: Bool?
    public init(op: String) { self.op = op }
    public static let reads: Set<String> = ["status", "lists", "search", "read"]
    public static let writes: Set<String> = ["create", "update", "complete", "delete"]
    public static func decode(_ data: Data) throws -> Request {
        let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]
        let keys: Set<String> = ["op", "request_id", "id", "list_id", "list_name", "query", "completed", "limit", "offset", "title", "notes", "due_date", "due_time", "timezone", "clear_due", "alarm", "minutes_before", "expected_version", "confirmed", "allow_shared"]
        guard Set(obj.keys).isSubset(of: keys) else { throw Failure("invalid_arguments", "Unknown argument.") }
        let r = try JSONDecoder().decode(Request.self, from: data)
        try r.validate()
        return r
    }
    public func validate() throws {
        guard Self.reads.union(Self.writes).contains(op) else { throw Failure("invalid_operation", "Unsupported operation.") }
        for (value, max) in [(title, 500), (notes, 20000), (query, 200), (id, 500), (list_id, 500), (list_name, 200)] {
            if let value, value.count > max { throw Failure("invalid_arguments", "Text exceeds the size limit.") }
        }
        if let title, title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { throw Failure("invalid_title", "Title cannot be empty.") }
        if let completed, !["pending", "completed", "all"].contains(completed) { throw Failure("invalid_arguments", "Invalid completed filter/state.") }
        if !(1...200).contains(limit ?? 50) || !(0...100000).contains(offset ?? 0) { throw Failure("invalid_arguments", "Invalid pagination.") }
        if let alarm, !["none", "at_due", "before_due"].contains(alarm) { throw Failure("invalid_alarm", "Use none, at_due or before_due.") }
        if alarm == "before_due" {
            guard let minutes_before, (1...525600).contains(minutes_before) else { throw Failure("invalid_alarm", "before_due needs 1...525600 minutes_before.") }
        } else if minutes_before != nil { throw Failure("invalid_alarm", "minutes_before requires before_due.") }
        if clear_due == true && (due_date != nil || due_time != nil || timezone != nil || (alarm != nil && alarm != "none")) { throw Failure("invalid_date", "clear_due conflicts with date, time, timezone or alarm.") }
        if due_time != nil && due_date == nil { throw Failure("invalid_date", "Time needs a date.") }
        if timezone != nil && due_date == nil { throw Failure("invalid_date", "Timezone needs a date; supply the complete desired date/time.") }
        if Self.writes.contains(op) {
            guard let request_id, UUID(uuidString: request_id) != nil else { throw Failure("invalid_request_id", "A stable UUID is required for every mutation; reuse it after timeouts.") }
            guard confirmed == true else { throw Failure("confirmation_required", "An explicit owner instruction or chat approval is required for this exact operation.") }
        }
        if op == "create" && (title == nil || list_id == nil || alarm == nil) { throw Failure("invalid_arguments", "Creation needs title, an explicit list_id and an explicit alarm choice.") }
        if ["read", "update", "complete", "delete"].contains(op) && (id ?? "").isEmpty { throw Failure("invalid_arguments", "An exact reminder id is required.") }
        if ["update", "complete", "delete"].contains(op) && (expected_version ?? "").isEmpty { throw Failure("version_required", "Read the reminder first and pass its version.") }
        if op == "complete" && !["pending", "completed"].contains(completed ?? "") { throw Failure("invalid_arguments", "Set completed to pending or completed, never toggle.") }
        if op == "update" && title == nil && notes == nil && list_id == nil && due_date == nil && clear_due != true && alarm == nil { throw Failure("invalid_arguments", "No changes supplied.") }
        _ = try DuePlan(request: self)
    }
}

public struct DuePlan {
    public let components: DateComponents?
    public let instant: Date?
    public init(request r: Request) throws {
        guard let day = r.due_date else { components = nil; instant = nil; return }
        let parts = day.split(separator: "-", omittingEmptySubsequences: false)
        guard day.count == 10, parts.count == 3, let y = Int(parts[0]), let m = Int(parts[1]), let d = Int(parts[2]), (1900...2200).contains(y) else { throw Failure("invalid_date", "Use YYYY-MM-DD, years 1900...2200.") }
        guard let zoneName = r.timezone, let zone = TimeZone(identifier: zoneName), zoneName == "UTC" || zoneName.contains("/") else { throw Failure("invalid_timezone", "Provide an IANA timezone, e.g. America/Mexico_City.") }
        var cal = Calendar(identifier: .gregorian); cal.timeZone = zone
        var c = DateComponents(); c.calendar = cal; c.timeZone = zone; c.year = y; c.month = m; c.day = d
        if let clock = r.due_time {
            let p = clock.split(separator: ":", omittingEmptySubsequences: false)
            guard clock.count == 5, p.count == 2, let h = Int(p[0]), let min = Int(p[1]), (0...23).contains(h), (0...59).contains(min) else { throw Failure("invalid_time", "Use HH:mm, 24-hour time.") }
            c.hour = h; c.minute = min; c.second = 0
        }
        guard let date = cal.date(from: c) else { throw Failure("invalid_date", "This date does not exist.") }
        let round = cal.dateComponents([.year, .month, .day, .hour, .minute], from: date)
        guard round.year == y && round.month == m && round.day == d && (c.hour == nil || (round.hour == c.hour && round.minute == c.minute)) else { throw Failure("invalid_date", "Invalid calendar date or nonexistent daylight-saving time.") }
        // A wall time in a repeated DST hour has two possible instants. Require another time.
        if c.hour != nil {
            let before = cal.startOfDay(for: date).addingTimeInterval(-1)
            var wall = DateComponents(); wall.hour = c.hour; wall.minute = c.minute; wall.second = 0
            let first = cal.nextDate(after: before, matching: wall, matchingPolicy: .strict, repeatedTimePolicy: .first)
            let last = cal.nextDate(after: before, matching: wall, matchingPolicy: .strict, repeatedTimePolicy: .last)
            if first != last { throw Failure("ambiguous_time", "This daylight-saving wall time repeats. Choose an unambiguous time.") }
        }
        components = c; instant = c.hour == nil ? nil : date
        if let alarm = r.alarm, alarm != "none", instant == nil { throw Failure("invalid_alarm", "A timed alarm needs a date, time and timezone.") }
    }
}

public func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
public func canonical(_ value: Any) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .fragmentsAllowed]) }
public func privateDirectory(_ dir: URL) throws {
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    let st = try FileManager.default.attributesOfItem(atPath: dir.path)
    guard st[.type] as? FileAttributeType == .typeDirectory, (st[.ownerAccountID] as? NSNumber)?.uint32Value == getuid() else { throw Failure("unsafe_storage", "Helper storage must be an owned directory, not a link.") }
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: dir.path)
}
public func durableWrite(_ data: Data, to url: URL) throws {
    let temp = url.deletingLastPathComponent().appendingPathComponent(".\(UUID().uuidString).tmp")
    let fd = open(temp.path, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW, 0o600)
    guard fd >= 0 else { throw Failure("storage_error", "Cannot create private journal.") }
    defer { close(fd); unlink(temp.path) }
    try data.withUnsafeBytes { raw in
        var pos = 0
        while pos < raw.count {
            let n = Darwin.write(fd, raw.baseAddress!.advanced(by: pos), raw.count - pos)
            guard n > 0 else { throw Failure("storage_error", "Cannot write journal.") }; pos += n
        }
    }
    guard fsync(fd) == 0, rename(temp.path, url.path) == 0 else { throw Failure("storage_error", "Cannot persist journal.") }
    let dfd = open(url.deletingLastPathComponent().path, O_RDONLY)
    defer { if dfd >= 0 { close(dfd) } }
    guard dfd >= 0, fsync(dfd) == 0 else { throw Failure("storage_error", "Cannot sync journal directory.") }
}

/// Serialized by the helper's single-request dispatcher. Writes pending BEFORE EventKit.
/// A crash after save blocks retries instead of creating another reminder.
public final class Journal {
    let dir: URL
    public init(directory: URL) throws { dir = directory; try privateDirectory(dir) }
    public func perform(_ r: Request, validate: () throws -> Void, save: () throws -> [String: Any]) throws -> [String: Any] {
        try r.validate()
        let raw = try JSONEncoder().encode(r)
        let hash = digest(try canonical(JSONSerialization.jsonObject(with: raw)))
        let path = dir.appendingPathComponent(r.request_id!.lowercased() + ".json")
        if FileManager.default.fileExists(atPath: path.path) {
            let old = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as? [String: Any] ?? [:]
            guard old["hash"] as? String == hash else { throw Failure("request_id_conflict", "This request_id was used for different arguments. Do not retry with a new id until the previous outcome is reconciled.") }
            if old["state"] as? String == "done", var result = old["result"] as? [String: Any] { result["replayed"] = true; return result }
            throw Failure("outcome_unknown", "A previous attempt may have committed. Read/search to reconcile; never retry creation with a new request_id.")
        }
        try validate()
        try durableWrite(try canonical(["hash": hash, "state": "pending", "operation": r.op]), to: path)
        let result = try save() // Any save error conservatively leaves pending; never auto retry.
        do { try durableWrite(try canonical(["hash": hash, "state": "done", "result": result]), to: path) }
        catch { throw Failure("outcome_unknown", "EventKit saved but the receipt could not be persisted. Read/search to reconcile; do not repeat with a new id.") }
        return result
    }
}

public enum ListPolicy {
    public static func classify(local: Bool, delegated: Bool, sourceID: String, name: String, binding: [String: String]?) -> [String: Any] {
        let valid = binding?["source_id"] == sourceID
        let cloud = !local && valid && binding?["kind"] == "icloud"
        return ["account_kind": local ? "local" : cloud ? "icloud" : "unverified_account",
                "classification_basis": cloud ? "owner_confirmed_locally" : "public_eventkit_metadata",
                "icloud_candidate": !local && name.caseInsensitiveCompare("iCloud") == .orderedSame,
                "sharing": delegated ? "delegated" : valid ? (binding?["sharing"] ?? "unknown") : "unknown",
                "sharing_basis": delegated ? "eventkit_isDelegate" : "owner_label_or_unknown"]
    }
    public static func requireWrite(_ info: [String: Any], writable: Bool, allowShared: Bool) throws {
        guard info["account_kind"] as? String == "icloud" else { throw Failure("unverified_icloud_list", "The owner must confirm this list belongs to iCloud in the local helper. Local/other accounts are not mutation targets.") }
        guard writable else { throw Failure("read_only_list", "The list does not allow changes.") }
        guard info["sharing"] as? String == "private" || allowShared else { throw Failure("shared_list_confirmation", "Sharing is shared, delegated or unknown. Explain possible disclosure to collaborators and obtain explicit approval before allow_shared=true.") }
    }
    public static func select<T>(_ all: [T], id: String?, name: String?, getID: (T) -> String, getName: (T) -> String) throws -> [T] {
        if let id {
            let found = all.filter { getID($0) == id }
            guard found.count == 1 else { throw Failure("list_not_found", "List id is stale or unavailable. List again; never substitute another account.") }
            if let name, getName(found[0]) != name { throw Failure("list_mismatch", "List id and name differ.") }
            return found
        }
        if let name {
            let found = all.filter { getName($0) == name }
            guard found.count == 1 else { throw Failure(found.isEmpty ? "list_not_found" : "ambiguous_list", "Use an exact list_id; names may repeat.") }
            return found
        }
        return all
    }
}
