// Credentials arrive through a private stdin pipe, never argv or a file.
import Foundation
import Security

let args = CommandLine.arguments
let services = ["icloud-mcp-macos.apple", "icloud-mcp-macos.oauth"]
guard args.count == 3, services.contains(args[1]), !args[2].isEmpty else { exit(2) }
let secret = FileHandle.standardInput.readDataToEndOfFile()
guard !secret.isEmpty, secret.count <= 4096 else { exit(2) }
let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: args[1], kSecAttrAccount as String: args[2]]
var result = SecItemUpdate(query as CFDictionary, [kSecValueData as String: secret] as CFDictionary)
if result == errSecItemNotFound {
    var item = query
    item[kSecValueData as String] = secret
    item[kSecAttrLabel as String] = "iCloud MCP for macOS — \(args[1])"
    result = SecItemAdd(item as CFDictionary, nil)
}
guard result == errSecSuccess else {
    FileHandle.standardError.write(Data("Keychain storage failed (status \(result)).\n".utf8))
    exit(1)
}
