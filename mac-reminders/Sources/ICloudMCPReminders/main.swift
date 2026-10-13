import AppKit
import EventKit
import Darwin
import RemindersCore

final class LocalSocket {
    let path: String
    let fd: Int32
    let lockFD: Int32
    init(root: URL) throws {
        try privateDirectory(root)
        path = root.appendingPathComponent("reminders.sock").path
        guard path.utf8.count < 104 else { throw Failure("socket_path", "Socket path is too long.") }
        lockFD = open(root.appendingPathComponent("helper.lock").path, O_CREAT | O_RDWR | O_NOFOLLOW, 0o600)
        guard lockFD >= 0, flock(lockFD, LOCK_EX | LOCK_NB) == 0 else { throw Failure("already_running", "Another helper is running.") }
        fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { throw Failure("socket_error", "Cannot create socket.") }
        // Only the holder of the process lock may remove a stale socket.
        unlink(path)
        var addr = sockaddr_un(); addr.sun_family = sa_family_t(AF_UNIX)
        withUnsafeMutableBytes(of: &addr.sun_path) { raw in
            raw.copyBytes(from: Array(path.utf8) + [0])
        }
        let rc = withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
        }
        guard rc == 0, chmod(path, 0o600) == 0, listen(fd, 8) == 0 else { throw Failure("socket_error", "Cannot bind private socket.") }
    }
    func run(store: ReminderStore) {
        DispatchQueue(label: "org.icloudmcp.macos.reminders.ipc").async {
            while true {
                let client = accept(self.fd, nil, nil)
                if client < 0 { continue }
                var uid: uid_t = 0; var gid: gid_t = 0
                guard getpeereid(client, &uid, &gid) == 0 && uid == getuid() else { close(client); continue }
                var timeout = timeval(tv_sec: 5, tv_usec: 0)
                setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
                setsockopt(client, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
                var noSig: Int32 = 1
                setsockopt(client, SOL_SOCKET, SO_NOSIGPIPE, &noSig, socklen_t(MemoryLayout<Int32>.size))
                var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
                while data.count <= 65536 && !data.contains(10) {
                    let n = Darwin.read(client, &buffer, buffer.count)
                    if n <= 0 { break }; data.append(contentsOf: buffer.prefix(n))
                }
                let done = DispatchSemaphore(value: 0)
                DispatchQueue.main.async {
                    Task { @MainActor in
                        let reply: [String: Any]
                        do {
                            guard data.count <= 65536, data.last == 10 else { throw Failure("invalid_request", "A bounded JSON line is required.") }
                            let request = try Request.decode(data)
                            reply = ["ok": true, "result": try await store.execute(request)]
                        } catch let failure as Failure {
                            reply = ["ok": false, "error": ["code": failure.code, "message": failure.message]]
                        } catch {
                            // No reminder contents or account information in logs/errors.
                            reply = ["ok": false, "error": ["code": "eventkit_error", "message": "Local operation failed (\((error as NSError).domain):\((error as NSError).code)). If a mutation started, reconcile before retrying; reuse request_id."]]
                        }
                        if var bytes = try? canonical(reply) {
                            bytes.append(10)
                            bytes.withUnsafeBytes { raw in
                                var pos = 0
                                while pos < raw.count {
                                    let n = Darwin.write(client, raw.baseAddress!.advanced(by: pos), raw.count - pos)
                                    if n <= 0 { break }; pos += n
                                }
                            }
                        }
                        close(client); done.signal()
                    }
                }
                done.wait() // Serializes every EventKit operation, including journal + save.
            }
        }
    }
}

@MainActor
final class Delegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var status: NSTextField!
    var lists: NSPopUpButton!
    var sharing: NSPopUpButton!
    var iCloud: NSButton!
    var store: ReminderStore!
    var socket: LocalSocket!
    var calendars: [EKCalendar] = []
    var menuItem: NSStatusItem!
    func applicationDidFinishLaunching(_ notification: Notification) {
        do {
            let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("iCloud-MCP-macOS/data/eventkit")
            try privateDirectory(root)
            store = try ReminderStore(root: root)
            socket = try LocalSocket(root: root)
            socket.run(store: store)
            buildWindow()
            menuItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
            menuItem.button?.title = "iCloud MCP R"
            let menu = NSMenu()
            menu.addItem(withTitle: "Configurar Recordatorios…", action: #selector(show), keyEquivalent: "").target = self
            menu.addItem(withTitle: "Salir", action: #selector(quit), keyEquivalent: "q").target = self
            menuItem.menu = menu
            refresh()
            if !CommandLine.arguments.contains("--background") || store.authorization == "not_determined" { show() }
        } catch { NSApp.terminate(nil) }
    }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        show(); return true
    }
    func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 620, height: 500), styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "iCloud MCP — Recordatorios"; window.isReleasedWhenClosed = false; window.center()
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.translatesAutoresizingMaskIntoConstraints = false; window.contentView!.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: window.contentView!.leadingAnchor, constant: 22), stack.trailingAnchor.constraint(equalTo: window.contentView!.trailingAnchor, constant: -22), stack.topAnchor.constraint(equalTo: window.contentView!.topAnchor, constant: 22)])
        status = NSTextField(wrappingLabelWithString: "")
        stack.addArrangedSubview(status)
        stack.addArrangedSubview(NSTextField(wrappingLabelWithString: "Este auxiliar usa solo EventKit para Recordatorios. No solicita permisos desde el chat. Guardar en el Mac no confirma sincronización ni avisos en tus dispositivos."))
        let access = NSButton(title: "Solicitar acceso a Recordatorios…", target: self, action: #selector(authorize)); stack.addArrangedSubview(access)
        let reload = NSButton(title: "Consultar listas", target: self, action: #selector(refresh)); stack.addArrangedSubview(reload)
        lists = NSPopUpButton(); lists.target = self; lists.action = #selector(selectionChanged); stack.addArrangedSubview(lists)
        iCloud = NSButton(checkboxWithTitle: "Confirmo que esta lista pertenece a mi cuenta de iCloud", target: nil, action: nil); stack.addArrangedSubview(iCloud)
        sharing = NSPopUpButton(); sharing.addItems(withTitles: ["No sé si se comparte", "Lista privada", "Lista compartida"]); stack.addArrangedSubview(sharing)
        let bind = NSButton(title: "Guardar identificación de esta lista", target: self, action: #selector(bindList)); stack.addArrangedSubview(bind)
    }
    @objc func show() { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true) }
    @objc func quit() { NSApp.terminate(nil) }
    @objc func authorize() {
        let alert = NSAlert(); alert.messageText = "¿Permitir acceso completo a Recordatorios?"
        alert.informativeText = "macOS concede lectura y escritura de todos tus recordatorios a esta app. El conector limita los cambios a las listas que identifiques como iCloud. Continúa solo si autorizaste ampliar el acceso de iCloud MCP."
        alert.addButton(withTitle: "Continuar"); alert.addButton(withTitle: "Cancelar")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        store.store.requestFullAccessToReminders { _, _ in DispatchQueue.main.async { self.refresh() } }
    }
    @objc func refresh() {
        status.stringValue = "Acceso: \(store.authorization). Auxiliar local activo."
        guard store.authorization == "full_access" else { return }
        store.store.reset(); calendars = store.store.calendars(for: .reminder)
        lists.removeAllItems(); lists.addItems(withTitles: calendars.map { "\($0.title) — \($0.source.title) [\($0.calendarIdentifier.prefix(8))]" }); selectionChanged()
    }
    @objc func selectionChanged() {
        guard calendars.indices.contains(lists.indexOfSelectedItem) else { return }
        let info = store.listInfo(calendars[lists.indexOfSelectedItem])
        iCloud.state = info["account_kind"] as? String == "icloud" ? .on : .off
        sharing.selectItem(at: ["unknown", "private", "shared"].firstIndex(of: info["sharing"] as? String ?? "unknown") ?? 0)
    }
    @objc func bindList() {
        guard calendars.indices.contains(lists.indexOfSelectedItem) else { return }
        let c = calendars[lists.indexOfSelectedItem]
        guard c.source.sourceType != .local || iCloud.state != .on else { status.stringValue = "EventKit identifica esta lista como local; no se puede marcar iCloud."; return }
        var bindings = store.bindings()
        if iCloud.state == .on {
            bindings[c.calendarIdentifier] = ["source_id": c.source.sourceIdentifier, "kind": "icloud", "sharing": ["unknown", "private", "shared"][sharing.indexOfSelectedItem]]
        } else { bindings.removeValue(forKey: c.calendarIdentifier) }
        do { try durableWrite(try canonical(bindings), to: store.root.appendingPathComponent("lists.json")); status.stringValue = "Identificación guardada. No se modificó ningún recordatorio." }
        catch { status.stringValue = "No se pudo guardar la identificación; no se habilitó esa lista." }
    }
}

umask(0o077)
if CommandLine.arguments.contains("--self-check") {
    print("{\"protocol\":1,\"backend\":\"EventKit\",\"permission_requested\":false}")
} else {
    MainActor.assumeIsolated {
        let app = NSApplication.shared
        let delegate = Delegate(); app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }
}
