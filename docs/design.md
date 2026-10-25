# System Design and Trade-offs

## 1. Goals and scope

Urumi provides one MCP gateway for multiple upstream Model Context Protocol (MCP) servers, with WooCommerce as its first business data source.

The gateway centralizes:

- Authentication and user identity.
- Role-based authorization and tool access.
- Upstream tool discovery and routing.
- Upstream credential handling.
- Dashboard chat and management operations.
- Audit logging and upstream failure reporting.

The project is designed as a team-oriented demonstration system. It has been developed locally using Windows, Docker Desktop, and k3d, and deployed to a single AWS EC2 instance running Ubuntu 24.04 and k3s.

The current deployment demonstrates the core gateway workflow. It is not a completed horizontally scalable or production-hardened service.

## 2. Architecture

### Logical architecture

```text
Team member / administrator
           |
           v
     Dashboard / MCP client
           |
           v
      Urumi Gateway
  Authentication and authorization
  Tool discovery and routing
  Chat agent and management API
  Audit log and SQLite state
           |
     +-----+---------+
     |       |       |
     v       v       v
 WooCommerce Notes Utilities
     MCP     MCP     MCP
     |
     v
 WordPress + MariaDB
```

The gateway aggregates upstream tools through `/mcp`. The management API and dashboard use `/api` and the gateway web root. Dashboard chat calls the gateway's shared tool-routing path as the signed-in user.

### Kubernetes namespaces

| Namespace | Workloads | External entry point |
|---|---|---|
| `gateway` | Gateway MCP endpoint, management API, dashboard, chat agent, SQLite state | Gateway ingress |
| `mcp-servers` | Notes and Utilities MCP servers | No direct public ingress intended |
| `store` | WordPress, MariaDB, WooCommerce MCP, bootstrap job | Store ingress, if enabled in the current deployment |

The current AWS deployment uses a single EC2 host and Traefik ingress. The gateway's observed public hostname is `gateway.54.235.55.63.nip.io`. The deployment uses HTTP; TLS is not configured.

The current gateway image is `gateway:0.4.1`. Application images are imported into the k3s container runtime rather than pulled from ECR.

### Deployment environments

| Area | Local development | AWS demonstration |
|---|---|---|
| Host | Windows development machine | AWS EC2 |
| Container environment | Docker Desktop | Container runtime managed by k3s |
| Kubernetes | k3d | k3s |
| Operating system | Windows host with Linux containers | Ubuntu 24.04 |
| Ingress | Traefik with local development hostnames | Traefik with a nip.io hostname |
| Transport | Local development configuration | HTTP; no TLS configured |
| Gateway state | Persistent volume in the local cluster | SQLite on a persistent volume |
| Image delivery | Local development image workflow | Images imported into the k3s container runtime |

## 3. Tool naming and discovery

Tools are published using the format:

`<server-slug>__<tool-name>`

For example:

`woocommerce__list_orders`

Server slugs disallow underscores, making the separator unambiguous. Prefixing tool names avoids collisions when different upstream servers expose tools with identical names.

The gateway refreshes enabled upstream tool lists using a default 10-second cache TTL. Discovery uses a 5-second timeout and refreshes multiple upstreams concurrently.

When an upstream cannot be reached, it is marked unreachable and contributes no tools to the current discovery result. Disabled servers are skipped. Admin-only tools are filtered from member discovery.

In the tested AWS deployment, Notes exposed three tools, Utilities exposed three tools, and WooCommerce exposed five tools, for a total of 11 tools.

## 4. Tool-call flow

1. A client sends an MCP request to `/mcp` with an `Authorization: Bearer <API key>` header.
2. The gateway validates the key and identifies the active user.
3. Tool discovery filters tools according to the user's role. Tool calls independently enforce the permission check.
4. The router resolves the `server__tool` name and loads the corresponding enabled upstream server record.
5. When configured, the gateway decrypts the upstream credential in memory and constructs the upstream authentication header.
6. The gateway opens an upstream MCP session and calls the tool within the configured timeout.
7. The gateway returns the result and records the outcome in the audit log.

The chat agent uses the shared gateway tool function as the signed-in user. The language model is not the authorization boundary: permission checks must be enforced by application code.

## 5. Permissions, API keys, and sessions

The roles are `admin` and `member`.

Admins can manage users, upstream servers, and audit records. Members can use permitted tools and manage their own API keys.

The following WooCommerce tools are admin-only by default:

- `woocommerce__create_product`
- `woocommerce__update_order_status`

The gateway filters these tools from member discovery and checks permissions again at call time. Hiding a tool in the UI alone is insufficient because an MCP client can construct its own call.

MCP API keys and dashboard sessions are separate credentials.

- API keys are shown once at creation and stored as SHA-256 hashes, with a visible prefix for identification.
- Human passwords are hashed with Argon2.
- Dashboard authentication uses a signed HttpOnly session cookie with an eight-hour lifetime and `SameSite=Lax`.
- The cookie's secure flag is configurable. Local development uses `cookieSecure: "false"` for HTTP development.

The deployed public dashboard currently uses HTTP. Secure cookie configuration alone would not make that deployment safe for production; HTTPS and the associated ingress configuration must also be implemented and tested.

## 6. Credentialed upstream URL changes

When an administrator changes the URL of an upstream that already has a stored credential, the update is rejected unless the credential is entered again.

This prevents a URL-only edit from silently carrying an existing credential to a new destination.

The URL-only update rejection was tested locally through the dashboard and returned HTTP 422.

This control is not a substitute for URL validation, network egress restrictions, or administrator trust. An administrator who knows an upstream credential can still configure a different destination and enter that credential again.

## 7. Credential storage

Upstream credentials are encrypted with Fernet before being stored in SQLite. The encryption key is supplied through Kubernetes Secret configuration.

Credentials are decrypted only when needed for an upstream request and are not returned to the dashboard or MCP client.

Kubernetes Secrets are sensitive configuration, not a complete secret-management solution. Restrict access to them and back up the Fernet key separately from database backups. Losing the key makes stored credentials unreadable; obtaining both the database and the key could expose the stored credentials.

## 8. SQLite and scaling

SQLite keeps the demonstration self-contained and avoids a separate state database service. Gateway state resides on persistent storage, and the deployment is configured as a single replica.

A local SQLite database on a ReadWriteOnce volume is not an appropriate shared write store for multiple active gateway replicas.

Production scaling would require moving shared gateway state to PostgreSQL or an equivalent database and implementing tested migration, backup, and restore procedures.

The AWS pod-replacement test demonstrated that previously recorded audit entries remained visible after the gateway pod was recreated. This does not prove recovery from node loss, volume loss, database corruption, or accidental deletion.

## 9. Timeouts and upstream failures

The default chart values are:

| Setting | Default |
|---|---:|
| Tool-list timeout | 5 seconds |
| Tool-call timeout | 10 seconds |
| Tool-list cache TTL | 10 seconds |

Calls that exceed the configured deadline return a readable error. Connection errors can mark an upstream unreachable; that server then contributes no tools to discovery.

### Verified AWS recovery test

Notes was scaled to zero replicas. The dashboard reported Notes as unreachable and showed zero Notes tools, while Utilities and WooCommerce remained connected. Restoring Notes to one replica returned the dashboard to three connected servers and 11 tools.

A separate test deleted the gateway pod. Kubernetes recreated the pod, and the replacement reached the ready state. Existing audit records remained visible.

These tests demonstrate recovery from the specific pod and upstream failures exercised. They do not establish high availability for the cluster or EC2 host.

Opening a fresh upstream connection per call simplifies recovery after restarts and avoids stale sessions, but adds handshake overhead.

## 10. Chat agent

The chat agent uses an OpenAI-compatible chat-completions API with tool calling.

The agent allows at most six model calls per question and truncates individual tool results passed to the model to 6,000 characters. Its system prompt instructs the model to treat tool results as data rather than instructions and not to guess a currency absent from a tool result.

These measures are guardrails, not proof against prompt injection or inaccurate summaries. Permissions are enforced outside the model, but an administrator's chat can still use admin-authorized tools.

### Verified cross-server chat test

A request asked for the day's order total in rupees. The chat agent called:

1. `woocommerce__list_orders`, which returned a demo order with a total of USD 250.
2. `utilities__convert_currency`, with an amount of 250, `USD` as the source currency, and `INR` as the target currency.

The Utilities tool returned `22000`, and the chat displayed `22,000 INR`.

This verifies cross-server tool routing. The conversion output was not independently verified as a live exchange rate. Important financial values should be checked against the structured tool output and the conversion source's actual behaviour.

## 11. WooCommerce integration

The WooCommerce MCP service uses the WooCommerce REST API rather than writing directly to MariaDB or executing shell commands inside the WordPress pod. This keeps WooCommerce validation and business logic in the request path.

The integration uses REST consumer credentials supplied through a Kubernetes Secret and the configured in-cluster HTTP and forwarded-protocol setup.

NetworkPolicies restrict selected pod-to-pod paths, but they do not encrypt network traffic. Review forwarded-HTTPS assumptions and the authentication design before using real customer data.

### Verified store recovery test

The MariaDB pod `mariadb-0` was deleted during testing. Kubernetes recreated it, and the existing five WooCommerce products were still available afterward.

This verifies the observed product data survived that pod replacement. It does not prove that backups can be restored after volume loss or database corruption.

## 12. Kubernetes hardening and policies

NetworkPolicy manifests are defined in the `store`, `mcp-servers`, and `gateway` charts. They constrain paths according to the selectors and allowed traffic defined in those manifests.

Gateway, Notes, Utilities, and WooCommerce MCP templates set non-root UID 10001, disable privilege escalation, drop Linux capabilities, and disable service-account-token automounting.

WordPress and MariaDB templates also disable service-account-token automounting but retain their upstream image runtime users. The WordPress bootstrap job uses UID 33 to match WordPress file ownership.

The presence of a NetworkPolicy resource does not prove effective isolation. Verify both permitted and denied paths after policy changes, and confirm the cluster networking implementation enforces the policies.

## 13. Local development and production boundary

Local development uses k3d, with host ports 80 and 443 forwarded to the cluster load balancer and Traefik ingress. `*.localtest.me` normally resolves to loopback.

The `scripts/dev.ps1` helper checks Docker, detects an Apache process that might own port 80, starts the cluster, and waits for workloads.

The AWS deployment differs from the local setup: it runs on Ubuntu 24.04 and k3s on an EC2 `t3.medium` instance in `us-east-1`, with Traefik and the current gateway nip.io hostname.

The current AWS demonstration does not have TLS configured. Production would require DNS and TLS, secure cookies, registry-hosted immutable images, reviewed storage, protected secrets, backups, monitoring, rate limits, and restricted network access. TLS and cert-manager are not fully templated by the current ingress manifests.

## 14. Trade-offs

| Decision | Benefit | Cost or limitation |
|---|---|---|
| SQLite | Simple, self-contained state | Single active writer; not suitable for horizontal scale |
| Fresh session per upstream call | Straightforward recovery | Additional handshake overhead |
| Prefixed tool names | Stable, unambiguous names | Longer tool names |
| Admin-only deny-list | Simple central rule | New tools may be member-visible until restricted |
| Shared upstream credentials | Simpler integration | Permitted tools may expose records beyond a member's own data |
| In-memory login throttle | No additional service | Resets on restart; not shared across replicas |
| Local HTTP | Easy development | No transport encryption |
| Dashboard served by gateway | One image and deployment | Frontend and backend deploy together |
| Single-node k3s | Lower demonstration complexity | No node-level high availability |

## 15. Known gaps and future work

- Complete TLS and cert-manager configuration.
- Enable secure cookies for HTTPS and review session/CSRF behaviour.
- Add confirmation for consequential chat-initiated writes.
- Consider allow-list permissions and per-user rate limits.
- Add management-action auditing, retention, and backup/restore tests.
- Tighten gateway egress and test NetworkPolicy enforcement.
- Move to PostgreSQL before scaling gateway replicas.
- Establish a repeatable image publishing and deployment pipeline.
- Test Helm upgrades and rollbacks.
- Implement OAuth-based MCP authorization and multi-store provisioning if needed.
- Add monitoring, alerting, and operational recovery procedures.

## Related documentation

- [README](../README.md)
- [Threat model and residual risks](threat-model.md)
- [AWS deployment and operations](aws-deployment.md)
