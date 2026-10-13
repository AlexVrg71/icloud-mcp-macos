# Release and validation — 0.1.0b1

Public repository: [https://github.com/AlexVrg71/icloud-mcp-macos](https://github.com/AlexVrg71/icloud-mcp-macos). Its history starts with a fresh source snapshot and excludes private deployment history. The package has not been published to PyPI.

## Release maintenance criteria

1. Review the snapshot and run `python3 scripts/check_public_tree.py`. The check detects common patterns, private files, and personal paths; it does not guarantee detection of every possible secret.
2. Preserve `LICENSE`, `UPSTREAM.txt`, and notices. Use public commit metadata or a GitHub noreply address. Do not import private deployment history.
3. Keep Private vulnerability reporting enabled and the `SECURITY.md` reporting channel current. Package metadata links to this repository.
4. Review the GitHub Actions workflow: synthetic tests only, `contents: read`, no secrets, and no automatic publishing. Check remote execution in [GitHub Actions](https://github.com/AlexVrg71/icloud-mcp-macos/actions/workflows/checks.yml); the local results below do not replace that status.
5. Publish only reviewed source and documentation. Exclude `.venv`, `.build`, `build`, `data`, logs, backups, configuration, secrets, compiled packages, and device evidence. Ad hoc development signing is not notarized distribution.

**Accepted omission:** a clean installation on another Mac. The maintainer chose to omit it, so it is a validation limitation rather than an outstanding release requirement. Public release preparation did not request account access or TCC permissions.

## Reproducible validation

See the [README](../README.md) for commands. The suite uses synthetic objects, temporary sockets, and in-memory HTTP transport. It never uses the running server, real Keychain, or the owner's reminders. The Keychain utility is compiled and its invocations are tested with mocks; interactive credential configuration is not executed as a test.

Regression coverage checks the previous 50 tools and the eight Reminders tools plus the clock when enabled. The read-only catalog is smaller. OAuth tests cover root and prefixed URLs, PKCE, rejected passwords, denial, and single-use codes. The Swift library checks dates/time zones, list permissions, UUIDs/versions, and uncertain results.

Update this document and `CHANGELOG.md` for each release. Do not remove the beta label or claim compatibility with other machines without evidence.

## Local preparation results

- 67 Python tests and 28 Swift tests: PASS. These include 21 new tests for installer portability, isolation, and policies.
- Root/prefixed OAuth, HTTP catalog, and synthetic downloads: PASS.
- EventKit bundle and native Keychain utility: build PASS. Local bundle signature verified; the app was not opened.
- Dependencies installed in a separate virtual environment; the functional installer was not run and the existing deployment was not changed.
- Source review and hygiene check: no outstanding findings. This does not certify that all possible secrets are absent.

`python3 scripts/package_source.py` generates a source ZIP in `dist/` with an internal `SHA256SUMS` file. It excludes `.git`, environments, executables, logs, and runtime data. Share that archive rather than a ZIP of the entire working directory.
