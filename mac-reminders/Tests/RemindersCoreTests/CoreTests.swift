import XCTest
@testable import RemindersCore

final class CoreTests: XCTestCase {
    func request() -> Request {
        var r = Request(op: "create"); r.title = "Ficticio"; r.list_id = "test-list"; r.request_id = UUID().uuidString
        r.confirmed = true; r.alarm = "none"; return r
    }
    func due(_ day: String = "2026-10-12", _ time: String? = "15:00", _ zone: String = "America/Mexico_City") -> Request {
        var r = request(); r.due_date = day; r.due_time = time; r.timezone = zone; return r
    }
    func testMexicoTimeMapsToUTCWithoutMacTimezone() throws {
        let p = try DuePlan(request: due())
        XCTAssertEqual(ISO8601DateFormatter().string(from: p.instant!), "2026-10-12T21:00:00Z")
        XCTAssertEqual(p.components?.timeZone?.identifier, "America/Mexico_City")
    }
    func testDateOnlyDoesNotInventTimeOrAlarm() throws {
        let p = try DuePlan(request: due("2026-10-12", nil)); XCTAssertNil(p.instant); XCTAssertNil(p.components?.hour)
    }
    func testInvalidCalendarDate() { XCTAssertThrowsError(try DuePlan(request: due("2026-02-30"))) }
    func testNonexistentDSTTime() { XCTAssertThrowsError(try DuePlan(request: due("2026-03-08", "02:30", "America/New_York"))) }
    func testAmbiguousDSTTime() { XCTAssertThrowsError(try DuePlan(request: due("2026-11-01", "01:30", "America/New_York"))) }
    func testUnknownTimezone() { XCTAssertThrowsError(try DuePlan(request: due("2026-10-12", "15:00", "Not/AZone"))) }
    func testMissingTimezone() { var r = due(); r.timezone = nil; XCTAssertThrowsError(try r.validate()) }
    func testTimeWithoutDateRefused() { var r = request(); r.due_time = "15:00"; XCTAssertThrowsError(try r.validate()) }
    func testDateOnlyTimedAlarmRefused() { var r = due("2026-10-12", nil); r.alarm = "at_due"; XCTAssertThrowsError(try r.validate()) }
    func testAlarmBeforeRequiresPositiveMinutes() { var r = due(); r.alarm = "before_due"; r.minutes_before = 0; XCTAssertThrowsError(try r.validate()) }
    func testClearDateConflicts() { var r = due(); r.clear_due = true; XCTAssertThrowsError(try r.validate()) }
    func testExplicitApprovalRequiredForEachMutation() {
        for op in Request.writes { var r = request(); r.op = op; r.confirmed = false; XCTAssertThrowsError(try r.validate()) }
    }
    func testCreationCannotUseImplicitList() { var r = request(); r.list_id = nil; XCTAssertThrowsError(try r.validate()) }
    func testMutationNeedsStableUUID() { var r = request(); r.request_id = "../bad"; XCTAssertThrowsError(try r.validate()) }
    func testReadBeforeUpdateDeleteAndComplete() {
        for op in ["update", "delete", "complete"] { var r = request(); r.op = op; r.id = "test"; XCTAssertThrowsError(try r.validate()) }
    }
    func testCompletionIsExplicitState() {
        var r = Request(op: "complete"); r.id = "test"; r.request_id = UUID().uuidString; r.confirmed = true; r.expected_version = "v"
        XCTAssertThrowsError(try r.validate()); r.completed = "completed"; XCTAssertNoThrow(try r.validate())
        r.completed = "pending"; XCTAssertNoThrow(try r.validate())
    }
    func testUnknownKeysAndOperationsRejected() {
        XCTAssertThrowsError(try Request.decode(Data(#"{"op":"status","script":"anything"}"#.utf8)))
        XCTAssertThrowsError(try Request.decode(Data(#"{"op":"request_permission"}"#.utf8)))
    }
    func testBadSearchLimitsRejected() { var r = Request(op: "search"); r.limit = 0; XCTAssertThrowsError(try r.validate()); r.limit = 201; XCTAssertThrowsError(try r.validate()) }
    func testJournalReplaySurvivesRestartWithoutSecondSave() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let r = request(); var saves = 0
        let result = try Journal(directory: dir).perform(r, validate: {}, save: { saves += 1; return ["id": "one"] })
        XCTAssertEqual(result["id"] as? String, "one")
        let replay = try Journal(directory: dir).perform(r, validate: { XCTFail("must replay before current version validation") }, save: { saves += 1; return [:] })
        XCTAssertEqual(saves, 1); XCTAssertEqual(replay["replayed"] as? Bool, true)
        let modes = try FileManager.default.attributesOfItem(atPath: dir.appendingPathComponent(r.request_id!.lowercased()+".json").path)
        XCTAssertEqual((modes[.posixPermissions] as? NSNumber)?.intValue, 0o600)
    }
    func testCrashOrSaveErrorBlocksRetry() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let r = request(); var saves = 0; let j = try Journal(directory: dir)
        XCTAssertThrowsError(try j.perform(r, validate: {}, save: { saves += 1; throw Failure("synthetic", "uncertain save") }))
        XCTAssertThrowsError(try Journal(directory: dir).perform(r, validate: {}, save: { saves += 1; return [:] }))
        XCTAssertEqual(saves, 1)
    }
    func testSameKeyDifferentPayloadRefused() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        var r = request(); let j = try Journal(directory: dir)
        _ = try j.perform(r, validate: {}, save: { ["id": "one"] }); r.title = "different"
        XCTAssertThrowsError(try j.perform(r, validate: {}, save: { XCTFail("no duplicate"); return [:] }))
    }
    func testDeniedOrConflictingValidationNeverSavesOrConsumesKey() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let r = request(); let j = try Journal(directory: dir)
        XCTAssertThrowsError(try j.perform(r, validate: { throw Failure("conflict", "changed") }, save: { XCTFail("no mutation"); return [:] }))
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: dir.path), [])
    }

    func testLocalNeverBecomesICloudByLabel() {
        let i = ListPolicy.classify(local: true, delegated: false, sourceID: "s", name: "iCloud", binding: ["source_id":"s", "kind":"icloud", "sharing":"private"])
        XCTAssertEqual(i["account_kind"] as? String, "local")
        XCTAssertThrowsError(try ListPolicy.requireWrite(i, writable: true, allowShared: true))
    }
    func testICloudNameIsCandidateNotProof() {
        let i = ListPolicy.classify(local: false, delegated: false, sourceID: "s", name: "iCloud", binding: nil)
        XCTAssertEqual(i["account_kind"] as? String, "unverified_account"); XCTAssertEqual(i["icloud_candidate"] as? Bool, true)
        XCTAssertThrowsError(try ListPolicy.requireWrite(i, writable: true, allowShared: true))
    }
    func testStaleBindingDoesNotAuthorizeAnotherSource() {
        let i = ListPolicy.classify(local: false, delegated: false, sourceID: "new", name: "iCloud", binding: ["source_id":"old", "kind":"icloud", "sharing":"private"])
        XCTAssertEqual(i["sharing"] as? String, "unknown"); XCTAssertThrowsError(try ListPolicy.requireWrite(i, writable: true, allowShared: false))
    }
    func testUnknownOrSharedRequiresDisclosureApproval() {
        for sharing in ["unknown", "shared"] {
            let i = ListPolicy.classify(local: false, delegated: false, sourceID: "s", name: "iCloud", binding: ["source_id":"s", "kind":"icloud", "sharing":sharing])
            XCTAssertThrowsError(try ListPolicy.requireWrite(i, writable: true, allowShared: false))
            XCTAssertNoThrow(try ListPolicy.requireWrite(i, writable: true, allowShared: true))
        }
    }
    func testDelegationOverridesPrivateLabelAndReadOnlyStillRefused() {
        let i = ListPolicy.classify(local: false, delegated: true, sourceID: "s", name: "iCloud", binding: ["source_id":"s", "kind":"icloud", "sharing":"private"])
        XCTAssertEqual(i["sharing"] as? String, "delegated")
        XCTAssertThrowsError(try ListPolicy.requireWrite(i, writable: true, allowShared: false))
        XCTAssertThrowsError(try ListPolicy.requireWrite(i, writable: false, allowShared: true))
    }
    func testDuplicateListNamesRequireIDAndStaleIDNeverFallsBack() throws {
        let lists = [["id":"a", "name":"Tasks"], ["id":"b", "name":"Tasks"]]
        func select(_ id: String?, _ name: String?) throws -> [[String:String]] { try ListPolicy.select(lists, id: id, name: name, getID: { $0["id"]! }, getName: { $0["name"]! }) }
        XCTAssertThrowsError(try select(nil, "Tasks")); XCTAssertThrowsError(try select("stale", "Tasks"))
        XCTAssertThrowsError(try select("a", "Wrong")); XCTAssertEqual(try select("b", "Tasks").count, 1)
    }
}
