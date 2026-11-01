# Remote setup: ChatGPT and Claude

This route follows [Mac preparation](../README.md#prepare-the-mac--both-routes). Do **not** run the local `configure` command first. If you already did, use [the migration section](#switching-an-existing-local-installation-to-remote).

GitHub hosts source code, not your iCloud server. You operate the server on your Mac. This guide uses public HTTPS with OAuth so both clients can reach it. OpenAI also offers [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels); it has separate access requirements and is not configured or validated by this guide.

## 1. Prepare a dedicated HTTPS address

The concrete example below uses [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel) on HTTPS port 443 with the entire hostname dedicated to this server. You do not need to purchase a domain. Install and sign into [Tailscale for macOS](https://tailscale.com/docs/install/mac), make its CLI available, and follow Tailscale's requirements for MagicDNS, HTTPS certificates, and Funnel permission. Package support can vary; consult those instructions if Funnel is unavailable.

Inspect existing routing before changing anything:

```sh
tailscale serve status
tailscale funnel status
```

If this machine's HTTPS port 443 or root path already serves something, **do not use this root-route example and do not run a reset**. Use a separate dedicated HTTPS hostname/proxy, or have the existing operator review a prefix configuration described below. Do not reuse another person's endpoint.

Find this machine's complete DNS name in the Tailscale admin console. Its HTTPS base URL is `https://` followed by that name, with no path or trailing slash. In the same Terminal session, run the following command and paste your own base URL when it waits for input:

```sh
read -r ICLOUD_MCP_PUBLIC_URL
```

This variable contains a public address, not a password. The hostname must match the one Funnel will advertise. The server's loopback port defaults to 8876; check whether it is occupied:

```sh
lsof -nP -iTCP:8876 -sTCP:LISTEN
```

No output normally means no listening process was found. If occupied, choose another unprivileged port and use it consistently in `configure --port`, Funnel's target, and the checks below. Do not stop an unrelated process.

## 2. Configure once, then start

From the cloned repository, with the base URL set:

```sh
python3 scripts/manage.py configure --enable-reminders --public-url "${ICLOUD_MCP_PUBLIC_URL:?Set your HTTPS base URL first}"
```

This starts **read-only**. For initial write access, add `--allow-writes`; add `--allow-send` for outgoing mail and `--allow-invites` for invitations. Add `--chat-approvals` only if you want sends approved solely by the client instead of a second server web page. These are options on this same command, not additional configure runs. Permanent mail deletion remains disabled.

Enter the Apple Account, IANA time zone, Apple app-specific password, and a separate OAuth owner password (12+ characters). Both passwords are hidden and entered twice. Configuration saves Keychain items but does not validate the account or publish the endpoint.

If Reminders is enabled, complete [local helper permission and list selection](../README.md#reminders-permissions) once. Start this edition's HTTP server:

```sh
python3 scripts/manage.py start
```

This installs its login LaunchAgent. The server listens on `127.0.0.1:8876`. Confirm OAuth protection locally:

```sh
curl --max-time 15 -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8876/mcp
```

Expect **401** without a token. A connection error means the server has not started; inspect this edition's private logs before proceeding. A Keychain prompt may need your attention. Do not paste logs containing account details or tokens into an issue.

## 3. Enable Funnel and verify HTTPS

The following command publishes the loopback service persistently. Run it only when you intend to make this OAuth-protected endpoint accessible from the Internet and have checked that the root route is unused:

```sh
tailscale funnel --bg --https=443 http://127.0.0.1:8876
tailscale funnel status
```

Complete any Tailscale enablement prompt yourself. Check that the advertised HTTPS base URL exactly matches your configured URL. See the [Funnel command reference](https://tailscale.com/docs/reference/tailscale-cli/funnel). Verify the public endpoint:

```sh
curl --max-time 15 -sS -o /dev/null -w '%{http_code}\n' "${ICLOUD_MCP_PUBLIC_URL:?Set your HTTPS base URL first}/mcp"
curl --max-time 15 -fsS "${ICLOUD_MCP_PUBLIC_URL}/.well-known/oauth-authorization-server"
```

Expect **401** for `/mcp`, and OAuth metadata with HTTPS endpoints on your hostname for discovery. Do not disable TLS verification. Confirm reachability from outside your private network too; local success alone does not prove the client's cloud can reach it. A login screen or a 401 does not prove iCloud credentials work; the authenticated health check comes next.

To withdraw **only the root route created in this example**, use `tailscale funnel --https=443 off`; do not use a global reset. `python3 scripts/manage.py stop` stops this edition's HTTP agent but does not change Tailscale routing. Neither command removes credentials or data.

## 4A. Connect ChatGPT

Current instructions checked on November 1, 2026 against [OpenAI's custom MCP guide](https://developers.openai.com/api/docs/guides/custom-mcp-server). UI labels and account/workspace policies can change.

1. On ChatGPT web, open **Plugins → + → Add custom MCP server**. If unavailable, check your account/workspace permissions; installing this repository cannot unlock the client feature.
2. Name it **iCloud MCP for macOS**. Select the URL connection and enter your base URL followed by `/mcp`.
3. Choose **OAuth** and **dynamic client registration (DCR)** if asked. This server implements registration; do not choose CIMD, mixed/no authentication, or paste your Apple password into client-ID/client-secret fields. No pre-generated client ID or secret is supplied by this package.
4. Review the warning, create the plugin, and complete OAuth on your own server's authorization page using the **OAuth owner password**, not the Apple password. Install/connect the resulting personal plugin if prompted.
5. Open its permissions and choose approval for changes (for example **Any changes**) or the stricter **Always ask**, where available. Check the effective setting rather than assuming the account default. `--chat-approvals` trusts this client policy; it does not independently prove approval.
6. Select the plugin with `@` in a new conversation and run [read-only validation](../README.md#first-connection-validation).

Use the plugin/app details to refresh tools after server configuration changes. If your workspace requires recreation or administrator publication, follow its policy. A missing write tool may mean server read-only mode or disabled client actions, not a broken connection. Do not assume custom-server availability on every client surface merely because a built-in iCloud plugin is available there.

## 4B. Connect Claude remotely

Based on [Anthropic's custom connector guide](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp), checked November 1, 2026:

1. Open **Customize → Connectors → + Add → Add custom connector**. Managed organizations may require an owner to add it first.
2. Enter **iCloud MCP for macOS** and your HTTPS `/mcp` URL. Review detected OAuth settings.
3. Choose **Sign in now** and **Register automatically** for the OAuth client. This server uses dynamic registration, not Claude's published client identity. Leave fixed request headers empty.
4. Add/connect it, then enter the OAuth owner password on your own server's page. Enable the connector for the conversation and retain prompts for write operations.
5. Run [read-only validation](../README.md#first-connection-validation). Reconnect or refresh the tool list after server policy changes.

Remote connectors are reached from Anthropic's infrastructure, including when configured in Claude Desktop. A private VPN-only address or localhost will not work for this route. This server is **single-owner**: do not share its owner password or publish one personal-account endpoint for an entire team. Each owner needs a separate deployment.

## Switching an existing local installation to remote

Do not rerun `install` or `configure`, and do not delete configuration to bypass their checks.

1. Prepare your dedicated HTTPS base URL as above. Fully quit the stdio client so it stops its server. If this edition already has an HTTP agent, stop it with `python3 scripts/manage.py stop`. Leave the separately running Reminders helper in place.
2. Open `~/Library/Application Support/iCloud-MCP-macOS/config.json` locally. Set `public_url` to your HTTPS base URL (without `/mcp`), keeping all other keys and the current port unless deliberately changing it. Preserve owner-only file permissions (0600). Never add passwords to this file.
3. Run `python3 scripts/manage.py rotate-credentials`. It asks for the Apple app-specific password again and the separate OAuth password; use hidden Terminal input. The Apple value can be the existing app-specific password or a new one you generated yourself.
4. Start HTTP and publish/check HTTPS using steps 2–3 above; skip initial `configure` and skip starting the helper again. Connect the remote client.
5. Remove only this server's stdio entry from Claude's configuration if switching that client to remote. Avoid running both server modes against the same state with writes enabled. Multiple clients may connect to the one HTTP server.

If you only want to enable writes, change the [policy booleans](OPERATIONS.md#policies-and-configuration-changes), restart, and refresh tools; there is no need to rotate credentials just for that.

## Existing reverse proxies and prefixes

For a dedicated hostname, forward the HTTPS root to the loopback server while preserving methods, request bodies, and required headers. `public_url` is the base; the MCP endpoint appends `/mcp`.

For a prefix such as `/icloud`, set the base URL accordingly and **strip the prefix** when proxying. Route client-requested RFC 8414/RFC 9728 discovery paths under `/.well-known/…` to this server as well. Exact rules depend on the client/proxy; do not overwrite another service's discovery. A dedicated hostname avoids that collision. This advanced route has synthetic prefix coverage, not a ready-made configuration for every proxy provider.

Keep EventKit's Unix socket private. Never expose administration or inherited helper ports. Temporary attachment links grant access by possession and must remain private.

## Troubleshooting and validation limits

| Symptom | Check |
| --- | --- |
| `Already configured` | Use the migration/policy steps; do not repeat initial setup. |
| `agent already exists` | Do not start twice; use this edition's `stop` then `start` when restarting. |
| Connection refused / 502 | Server startup, private logs, Keychain unlock, port, and Funnel target. |
| Discovery 404 or wrong login URL | Base URL, root versus prefix forwarding, and discovery routing. |
| OAuth registration fails | Choose DCR/automatic registration, verify the callback is supported; do not disable authentication or redirect validation. |
| Authorization page rejects password | Use the separate OAuth owner password; rotate through Terminal if needed. |
| No write tools | `read_only`, send/invite flags, client action permissions, then refresh/reconnect. |
| Reminders denied/unavailable | Signed-in Mac session, local permission, running helper, and selected iCloud lists. |
| Works locally but not from client | Public DNS/HTTPS reachability and client/workspace restrictions. |

Keep the Mac awake, connected, and signed in. The installer does not change sleep, automatic login, or security settings. A saved reminder can wait for sync while offline. Neither a local save nor a successful health check proves device delivery.

This guide has been checked against source code and synthetic tests. It does not claim a new end-to-end installation or connection test in either client. The agreed omission of a clean install on another Mac remains unchanged.
