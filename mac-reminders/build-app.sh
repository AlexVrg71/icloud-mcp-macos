#!/bin/zsh
set -eu
cd "${0:A:h}"
export CLANG_MODULE_CACHE_PATH="$PWD/.build/clang-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$PWD/.build/swift-cache"
swift build --disable-sandbox --cache-path "$PWD/.build/package-cache"
app="$PWD/build/iCloud MCP Reminders.app"
mkdir -p "$app/Contents/MacOS"
cp .build/debug/ICloudMCPReminders "$app/Contents/MacOS/ICloudMCPReminders"
cp Info.plist "$app/Contents/Info.plist"
# Local development signature. Updates may require renewing the TCC grant.
# No certificates, Keychain items or security settings are created by this script.
codesign --force --sign - --identifier org.icloudmcp.macos.reminders "$app"
codesign --verify --strict "$app"
printf '%s\n' "$app"
