# System design and trade-offs

## Goals and scope

Urumi provides one MCP endpoint for multiple upstream MCP servers, using WooCommerce as the first data source. It keeps upstream credentials behind the gateway, applies per-user permissions, records tool outcomes, and handles upstream failures without unnecessarily disabling the other servers. It is designed as a team-sized, single-replica demo—not a completed horizontally scaled production service.

## Architecture

| Namespace | Workloads | External entry point |
|---|---|---|
| `store` | WordPress, MariaDB, WooCommerce MCP, bootstrap job | Store ingress |
| `mcp-servers` | Notes and Utilities MCP servers | None intended |
| `gateway` | MCP endpoint, management API, dashboard, chat agent, SQLite state | Gateway ingress |

The gateway aggregates upstream tools behind `/mcp`; the management API and dashboard use `/api` and the gateway web root. Dashboard chat uses the same tool-routing and authorization path as external MCP calls.

## Tool naming and discovery

Tools are published as `<server-slug>__<tool-name>`, such as `woocommerce__list_orders`. Server slugs disallow underscores, making the separator unambiguous. Prefixing every tool keeps names stable when another upstream exposes an identically named tool.

The gateway refreshes enabled upstream tool lists using a 10-second cache TTL by default. Discovery uses a 5-second timeout and refreshes multiple upstreams concurrently. Failed upstreams are marked unreachable and contribute no tools to the current listing. Disabled servers are skipped. Admin-only tools are filtered from member discovery.

## Tool-call flow

1. A client sends an MCP request to `/mcp` with `Authorization: Bearer <API key>`.
2. The gateway validates the key and identifies its active user.
3. Tool discovery filters tools for the user's role; tool calls also enforce the permission check.
4. The router resolves the `server__tool` name and loads the enabled server record.
5. The gateway decrypts that server's credential into memory, when configured, and builds the upstream authentication header.
6. It opens an upstream MCP session and calls the tool under the configured timeout.
7. The result is returned and the outcome is written to the audit log.

The chat agent calls the shared gateway tool function as the signed-in user. The LLM and dashboard are not the authorization boundary.

## Permissions, API keys, and sessions

The roles are `admin` and `member`. Admins can manage users, upstream servers, and audit records. Members can use permitted tools and manage their own keys. By default these tools are admin-only:
- `woocommerce__create_product`
- `woocommerce__update_order_status`

The gateway filters these tools from member discovery and enforces restrictions at call time. Hiding a tool in the UI alone would not be sufficient because an MCP client can construct its own call.

MCP API keys and dashboard sessions are separate credentials. API keys are shown once and stored as SHA-256 hashes, with a visible prefix for identification. Random high-entropy API keys differ from human passwords, which are hashed with Argon2. Dashboard authentication uses a signed HttpOnly session cookie, with an eight-hour lifetime and `SameSite=Lax` configured. The local chart uses `cookieSecure: "false"` for HTTP development; production should use HTTPS and set it to `"true"`.

## Credential storage

Upstream credentials are encrypted with Fernet before being stored in SQLite. The encryption key is supplied through Kubernetes Secret configuration. Credentials are decrypted only for the upstream request and are not returned to the dashboard or MCP client.

Kubernetes Secrets remain sensitive configuration, not a complete secret-management solution. Protect their access, and back up the Fernet key separately from database backups; losing the key makes stored credentials unreadable.

## SQLite and scaling

SQLite avoids a separate state database service and keeps the demo self-contained. The gateway state resides on persistent storage and the deployment is single-replica. A local SQLite database on a ReadWriteOnce volume is not an appropriate shared write store for multiple active replicas. Production scaling should move gateway state to PostgreSQL (or equivalent) and add tested migration, backup, and restore procedures.

## Timeouts and upstream failures

The default chart values are a 5-second tool-list timeout, a 10-second call timeout, and a 10-second listing cache TTL. Calls that exceed the deadline return a readable error. Connection errors can mark the upstream unreachable; that server then contributes no tools to discovery.

In testing, scaling Notes to zero caused the dashboard to report it unreachable while Utilities and WooCommerce remained connected. Scaling Notes back up restored it.

Opening a fresh upstream connection per call simplifies recovery after restarts and avoids stale sessions, but adds handshake overhead.

## Chat agent

The chat agent uses an OpenAI-compatible chat-completions API with tool calling. It allows at most six model calls per question and truncates individual tool results passed to the model to 6,000 characters. Its system prompt tells the model to treat tool results as data, not instructions, and not to guess a currency that was absent from a tool result.

These are guardrails, not proof against prompt injection or inaccurate summaries. Permissions are enforced outside the model, but an admin's chat can still use admin-authorized tools. The tool trace helps inspect behavior. In one test, the conversion tool returned a numeric INR result that did not match the model's displayed total; verify important numbers against structured tool output.

## WooCommerce integration

The WooCommerce MCP service uses the WooCommerce REST API rather than writing directly to MariaDB or running shell commands inside the WordPress pod. This keeps WooCommerce validation and business logic in the request path.

The current integration uses REST consumer credentials from a Kubernetes Secret and the local in-cluster HTTP/forwarded-protocol configuration. NetworkPolicies restrict which pods can connect, but they do not encrypt traffic. Review forwarded-HTTPS assumptions and consider OAuth 1.0a signing or a transport-encryption design before using real customer data.

## Kubernetes hardening and policies

NetworkPolicy manifests are defined in the `store`, `mcp-servers`, and `gateway` charts. They constrain paths according to the selectors and allowed traffic in the manifests. Verify both permitted and denied paths after policy changes; the presence of policy resources alone does not prove effective isolation.

Gateway, Notes, Utilities, and WooCommerce MCP templates set non-root UID 10001, disable privilege escalation, drop Linux capabilities, and disable service-account-token automounting. WordPress and MariaDB templates also disable token automounting, but retain their upstream image runtime users. The WordPress bootstrap job uses UID 33 to match WordPress file ownership.

## Local development and production boundary

Local development uses k3d, forwarding host ports 80 and 443 to the cluster load balancer and Traefik ingress. `*.localtest.me` normally resolves to loopback. `scripts/dev.ps1` checks Docker, detects an Apache process that might own port 80, starts the cluster, and waits for workloads.

Production requires DNS and TLS, secure cookies, registry-hosted immutable images, a reviewed storage class, protected secrets, backups, monitoring, rate limits, and restricted network access. TLS/cert-manager is not fully templated by the current ingress manifests. Do not expose the local HTTP configuration publicly.

## Trade-offs

| Decision | Benefit | Cost / limitation |
|---|---|---|
| SQLite | Simple, self-contained | Single active writer; not suitable for horizontal scale |
| Fresh session per upstream call | Straightforward recovery | Handshake overhead |
| Always-prefixed tool names | Stable and unambiguous | Longer names |
| Admin-only deny-list | Simple central rule | New tools may be member-visible until restricted |
| Shared upstream credentials | Simpler integration | Members may access all records exposed by permitted tools |
| In-memory login throttle | No extra service | Resets on restart; not shared across replicas |
| Local HTTP | Easy development | No transport encryption |
| Dashboard served by gateway | One image/deployment | Frontend and backend deploy together |

## Known gaps and future work

- Require the upstream credential to be re-entered when changing a credentialed server's URL.
- Complete TLS/cert-manager configuration.
- Add confirmation for consequential chat-initiated writes.
- Consider allow-list permissions and per-user rate limits.
- Add management-action auditing, retention, backup, and restore tests.
- Move to PostgreSQL before scaling gateway replicas.
- Implement OAuth-based MCP authorization and multi-store provisioning if needed.
