// swift-tools-version: 5.9
import PackageDescription
let package = Package(name: "ICloudMCPReminders", platforms: [.macOS(.v14)], products: [
    .executable(name: "ICloudMCPReminders", targets: ["ICloudMCPReminders"])
], targets: [
    .target(name: "RemindersCore"),
    .executableTarget(name: "ICloudMCPReminders", dependencies: ["RemindersCore"]),
    .testTarget(name: "RemindersCoreTests", dependencies: ["RemindersCore"])
])
