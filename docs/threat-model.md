# Threat model

## Scope and assumptions

In scope are the gateway (`/mcp`, `/api`, dashboard, and chat agent), upstream MCP servers, the WooCommerce demo store, and Kubernetes configuration in this repository. The local cluster and host are treated as trusted demo infrastructure. Admins are trusted to register upstreams but may make mistakes. The LLM provider is external.

Local traffic uses HTTP. A public deployment would require an explicit TLS and access-control setup. This document is not a formal security audit.

## Assets

- Dashboard credentials and sessions.
- Member API keys and role assignments.
- WooCommerce REST credentials and the Utilities bearer token.
- Product, order, and customer data.
- Upstream registry and gateway SQLite database.
- Audit log.
- LLM provider key, quota, and availability.

## Trust boundaries

1. Browser/MCP client to gateway ingress.
2. Gateway authentication and authorization.
3. Gateway to each upstream.
4. Gateway to the LLM provider.
5. Pod-to-pod connectivity across `gateway`, `mcp-servers`, and `store`.
6. Administrator-controlled upstream registration and updates.

## Threats and mitigations

### Stolen API key

**Impact:** An attacker with an active key can act as that user within the user's permissions.

**Controls:** Raw keys are shown only when created; the database stores SHA-256 hashes and a visible key prefix; authentication checks key/user state; keys can be revoked. A revoked key was tested and returned HTTP 401.

**Residual risk:** A stolen active key works until revoked. Use a separate key per client and revoke/rotate it after suspected exposure.

### Member invokes an admin-only tool

**Impact:** A member could try to create products or change order status.

**Controls:** The gateway filters `woocommerce__create_product` and `woocommerce__update_order_status` from member discovery by default and separately checks permissions at call time. A member attempt to call an admin-only tool was denied and recorded in audit activity.

**Residual risk:** This is a deny-list. A newly added tool may be member-visible unless it is explicitly restricted. Review permissions whenever tools change.

### Cross-user API-key access

**Impact:** One member might obtain or revoke another member's API key.

**Controls:** Key-management endpoints enforce ownership, with broader rights for admins. Members should only see and revoke their own keys.

**Residual risk:** Add regression tests for cross-user access as the API evolves.

### Shared upstream credentials and store data

**Impact:** Members do not see the WooCommerce credential, but calls to member-visible tools execute using the gateway's shared upstream credential. A member may be able to read any orders/products exposed by those tools, not merely records belonging to that member.

**Controls:** The gateway encrypts upstream credentials at rest and never returns them to clients; admin-only write tools are restricted; calls are audited; WooCommerce results are trimmed to limit unnecessary customer detail.

**Residual risk:** Tool permissions are not record-level authorization. The upstream key is broader than each member needs. Do not use real customer data until least-privilege credentials or record-scoping rules are in place.

### Malicious upstream or prompt injection

**Impact:** Tool descriptions or stored data can contain instructions designed to manipulate the model, leak context, or trigger unintended actions.

**Controls:** Only admins can register servers; permissions are checked outside the model; calls have timeouts; the chat loop allows at most six model calls per question; each tool result passed back to the model is limited to 6,000 characters; the prompt tells the model to treat tool results as data; the dashboard exposes a tool trace.

**Residual risk:** Prompt wording is not a security boundary. An admin's chat can use admin-authorized tools, and a confirmation step before every write is not currently claimed. Consider confirmation for consequential changes and validate arguments in application code.

### SSRF through an upstream URL

**Impact:** A registered URL could target loopback, cloud metadata, or other sensitive addresses.

**Controls:** URL validation requires HTTP/HTTPS and rejects resolved addresses classified as loopback, link-local, unspecified, multicast, or reserved when a server is registered or its URL updated. NetworkPolicies provide a separate network-level control.

**Residual risk:** Registration-time validation cannot eliminate DNS rebinding, redirects, changed DNS answers, or every private/internal destination. Keep URL validation and NetworkPolicy testing separate; one does not replace the other.

### Credential retained after a URL change

**Impact:** If a stored credential is silently reused after an upstream URL changes, it could be sent to an unintended destination.

**Controls:** Changing the URL of a credentialed upstream requires entering its credential again. A URL-only update was tested through the dashboard and rejected with HTTP 422; the original URL and Bearer-token configuration remained unchanged.

**Residual risk:** An administrator who knows the upstream credential can still configure another destination and enter that credential again. URL validation and NetworkPolicy/egress restrictions remain important independent controls.
### Slow or unavailable upstream

**Impact:** A dead server could block tool discovery or chats.

**Controls:** Tool discovery defaults to a 5-second timeout, calls to a 10-second timeout, and the discovery cache TTL to 10 seconds. Failed upstreams are marked unreachable and don't contribute tools to discovery. Scaling Notes to zero was tested: the dashboard marked it unreachable while Utilities and WooCommerce remained connected. Restoring Notes recovered it.

**Residual risk:** This is not a high-availability deployment. Cluster or gateway outages can interrupt all gateway-mediated work.

### Dashboard session theft or insecure transport

**Impact:** A stolen session can be used as the signed-in user; plain HTTP traffic can expose credentials or session data to a network observer.

**Controls:** Dashboard sessions are signed, have an eight-hour lifetime, and use an HttpOnly cookie with `SameSite=Lax`. The cookie's secure flag is configurable.

**Residual risk:** Local development uses `cookieSecure: "false"`. Production should use HTTPS and set it to `"true"`. Review CSRF behavior and session invalidation before public exposure.

### Kubernetes lateral movement and service-account tokens

**Impact:** A compromised pod may try to contact unrelated services or use a mounted Kubernetes API token.

**Controls:** NetworkPolicy manifests exist in all three charts. Pod templates disable service-account-token automounting. Gateway, Notes, Utilities, and WooCommerce MCP are configured to run as UID 10001, with privilege escalation disabled and Linux capabilities dropped. WordPress and MariaDB also disable token automounting but retain their upstream image users.

**Residual risk:** Effective isolation depends on selectors, CNI enforcement, and allowed traffic rules. Do not claim every unauthorized connection is blocked without completed negative tests. NetworkPolicies do not encrypt traffic.

### LLM key and cost abuse

**Impact:** A leaked provider key or excessive chat requests could consume quota or incur costs.

**Controls:** The provider key is supplied through a Kubernetes Secret; the agent has a bounded tool loop and result-size cap.

**Residual risk:** Comprehensive per-user rate limiting and spend controls are not claimed as implemented. Use provider budgets/alerts and add request rate limits before broader deployment.

### Database and encryption-key exposure

**Impact:** A database copy can expose account/server/audit records; a database and Fernet key together can expose encrypted upstream credentials.

**Controls:** Passwords use Argon2 hashes, API keys are SHA-256 hashed, upstream credentials are Fernet encrypted, and gateway state lives on persistent storage.

**Residual risk:** Anyone who obtains both the database and encryption key may decrypt upstream credentials. Restrict and back up the key separately. SQLite on one volume is not a high-availability database.

### Data sent to the model provider

**Impact:** Tool results can include store information sent to the configured external model provider.

**Controls:** WooCommerce responses are trimmed and the LLM key is not exposed to the browser.

**Residual risk:** Returned names, items, and totals may still be sent to the provider. Avoid real customer data and review provider data handling before using production records.

## Why client keys are not forwarded upstream

A Urumi API key authenticates a user to Urumi. Forwarding it upstream would ask a server to trust a token it did not issue, spread a gateway credential into another trust boundary, and allow a compromised upstream to capture a token usable against Urumi. Instead, Urumi authenticates the user, enforces the user's permissions, and authenticates itself to each upstream with that upstream's own credential.

## Verification performed

Observed local results:
- A revoked API key returned HTTP 401.
- Member discovery exposed nine tools; the two default admin-only WooCommerce tools were excluded.
- A member's admin-only tool call was denied and appeared in audit activity.
- Disabling Utilities removed its tools from discovery; re-enabling it restored all 11 tools.
- Scaling Notes to zero showed it unreachable while the other upstreams remained connected; scaling Notes back up recovered it.
- Audit activity showed user attribution and chat tool calls.
- Source inspection confirmed the configured non-root and capability restrictions for gateway, Notes, Utilities, and WooCommerce MCP, and service-account-token automounting is disabled in the relevant templates. Source inspection is not a penetration test.

Only add claims about other security tests (such as specific SSRF payloads or every NetworkPolicy-denial scenario) after actually running and observing them.

## Highest-priority future work

1. Complete TLS/cert-manager setup and enable secure cookies.
2. Require confirmation for consequential chat-initiated writes.
3. Consider allow-list permissions and per-user rate limits.
4. Audit management actions; define audit retention and backup/restore procedures.
5. Tighten gateway egress and test NetworkPolicy enforcement.
6. Move to PostgreSQL before scaling gateway replicas.
7. Review WooCommerce authentication/forwarded-HTTPS behavior before handling real customer data.
