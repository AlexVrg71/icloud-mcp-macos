# Connecting ChatGPT, Claude, and other MCP clients

The repository does not create a hosted service on GitHub. The server runs on the owner's Mac, with a stable HTTPS address reachable by the MCP client. DNS, tunnels, and proxies remain under the operator's control: the installer does not change Tailscale, routers, or existing services.

## Initial setup

After `install` and before the first `configure`, prepare your own domain/proxy. This example intentionally uses a non-working domain:

```sh
python3 scripts/manage.py configure --enable-reminders --public-url https://mcp.example.invalid --allow-writes
```

Replace the domain with yours. Add `--allow-send` for outgoing mail, `--allow-invites` for invitations, and `--chat-approvals` if sends will rely solely on client approval. Without `--allow-writes`, the catalog is read-only. `configure` prompts in Terminal for the Apple app-specific password and a different OAuth password (at least 12 characters), both hidden and entered twice. It does not validate credentials or publish the service.

```sh
python3 scripts/manage.py start --helper
python3 scripts/manage.py open-reminders
python3 scripts/manage.py start
```

`start` registers only this edition's LaunchAgent. By default, the server listens on **127.0.0.1:8876**; use `--port` during `configure` if that port is occupied. Do not expose the EventKit socket or forward administration or inherited helper ports.

## Proxy requirements

For a dedicated domain, forward its HTTPS root to the loopback server, preserving the method, body, and required headers. The endpoint is `https://YOUR-DOMAIN/mcp`; `public_url` is the base URL without `/mcp`.

For a prefix such as `/icloud`, set `public_url=https://YOUR-DOMAIN/icloud` and configure the proxy to **strip that prefix** before forwarding. You must also route the client's RFC 8414/RFC 9728 OAuth discovery requests under `/.well-known/…` to the correct server. Exact paths depend on the client and proxy; do not overwrite discovery for another service using the domain. A dedicated subdomain avoids this collision. Root/prefix behavior is tested using synthetic ASGI transport, not every tunnel provider.

TLS is required for remote access. Do not disable certificate validation or use the internal HTTP port as an Internet endpoint. OAuth protects MCP; approval and registration pages are part of that flow. Temporary attachment links grant access by possession and must be treated as private.

## Connecting the client

The connection is to the MCP server, independent of a Dot or any custom assistant. Use it from an ordinary conversation or your preferred assistant. Each client controls tool discovery, approval presentation, and remote connection support; the server uses the same protocol and access limits.

Add the `/mcp` URL as a remote MCP server and complete OAuth using the **owner password**, not the Apple password. Configure write approval and refresh the tools. ChatGPT's option labels may vary; use the connector's tool-refresh action. The tool count depends on `read_only` and enabled features; the complete catalog for the four areas plus the clock contains 59 tools.

Start with diagnostics and list reads. Tests that create, send, or delete data require an explicit instruction. A successful diagnostic does not prove iPhone synchronization or notifications.

## Availability limitations

The Mac and its user session must be available; Keychain may need unlocking after a restart. `start` does not change sleep, automatic login, or system security settings. Run `stop` before changing the URL/port, then run `start` again. A URL change may require reconnecting OAuth in the client.
