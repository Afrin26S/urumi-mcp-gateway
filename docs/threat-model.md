# Threat Model

## 1. Scope and assumptions

This threat model covers:

- The Urumi gateway, including `/mcp`, `/api`, the dashboard, and chat agent.
- Upstream MCP servers: WooCommerce, Notes, and Utilities.
- The WordPress and WooCommerce demonstration store.
- Gateway SQLite state, audit records, and stored upstream credentials.
- Kubernetes configuration in the repository.
- Requests and results sent to the configured external language-model provider.

The local cluster and host are treated as trusted demonstration infrastructure. Administrators are trusted to register upstreams but may make mistakes. The language-model provider is external.

The current AWS deployment runs on a single EC2 instance with k3s and Traefik. Its public gateway hostname is `gateway.54.235.55.63.nip.io`, and its transport is HTTP without configured TLS.

This document is not a formal security audit. Implementation controls, locally observed tests, and AWS deployment tests are distinguished where relevant.

## 2. Assets

The primary assets are:

- Dashboard credentials, session cookies, and account identities.
- Member API keys, roles, and permissions.
- WooCommerce REST credentials and the Utilities bearer token.
- Product, order, and customer data.
- Upstream server registry and gateway SQLite database.
- Audit log and user activity records.
- Fernet encryption key used for stored upstream credentials.
- Language-model provider key, quota, and availability.
- Kubernetes Secrets, application configuration, and persistent volumes.
- Availability of the gateway and its upstream services.

## 3. Trust boundaries

1. Browser or MCP client to gateway ingress.
2. Gateway authentication and authorization.
3. Gateway to each upstream MCP server.
4. Gateway to the external language-model provider.
5. Pod-to-pod connectivity across `gateway`, `mcp-servers`, and `store`.
6. Administrator-controlled upstream registration and configuration updates.
7. Application state and credentials stored in SQLite, Kubernetes Secrets, and persistent volumes.

Each boundary requires its own controls. For example, a permission check does not replace transport encryption, and a NetworkPolicy does not encrypt traffic.

## 4. Threats, controls, and residual risks

### 4.1 Stolen API key

**Impact:** An attacker with an active key may act as the associated user within that user's permissions.

**Controls:**

- Raw API keys are shown only when created.
- Stored API keys use SHA-256 hashes and a visible prefix for identification.
- Authentication checks key and user state.
- Keys can be revoked.
- A revoked-key test returned HTTP 401 in local testing.

**Residual risk:** A stolen active key may be used until revoked. Create separate keys for different clients, avoid sharing them, and revoke or rotate them after suspected exposure.

### 4.2 Member invokes an admin-only tool

**Impact:** A member might attempt to create products or change order status without authorization.

**Controls:**

- `woocommerce__create_product` and `woocommerce__update_order_status` are admin-only by default.
- The gateway filters these tools from member discovery.
- The gateway checks permissions again at call time.
- A member attempt to invoke an admin-only tool was denied and recorded in audit activity during local testing.

**Residual risk:** The current rule is a deny-list. A newly added tool may be available to members unless explicitly restricted. Review and test permissions whenever the tool set changes.

### 4.3 Cross-user API-key access

**Impact:** A member could attempt to view, manage, or revoke another member's API key.

**Controls:**

- Key-management endpoints enforce ownership.
- Administrative operations have broader permissions than member operations.
- Members should only be able to view and revoke their own keys.

**Residual risk:** Add and maintain regression tests for cross-user access as the API evolves. Do not rely solely on hiding controls in the dashboard.

### 4.4 Shared upstream credentials and store data

**Impact:** Members do not receive the WooCommerce credential directly, but calls to member-visible tools execute using the gateway's shared upstream credential. A member may be able to read records exposed by those tools beyond records belonging to that member.

**Controls:**

- Upstream credentials are encrypted at rest.
- Credentials are not returned to clients.
- Admin-only write tools are restricted by default.
- Tool calls are audited.
- WooCommerce results are trimmed to reduce unnecessary customer detail.

**Residual risk:** Tool-level authorization is not record-level authorization. The upstream credential may grant broader access than any one member needs. Do not use real customer data until least-privilege credentials or record-scoping rules are in place.

### 4.5 Malicious upstream or prompt injection

**Impact:** Tool descriptions, product data, order information, or other upstream content could contain instructions intended to manipulate the model, expose context, or trigger unintended actions.

**Controls:**

- Only administrators can register upstream servers.
- Authorization checks are performed outside the model.
- Tool calls use timeouts.
- The chat loop permits at most six model calls per question.
- Individual tool results passed back to the model are limited to 6,000 characters.
- The system prompt instructs the model to treat tool results as data rather than instructions.
- The dashboard exposes a tool trace for inspection.

**Residual risk:** Prompt wording is not a security boundary. An administrator's chat can use admin-authorized tools, and confirmation for consequential chat-initiated writes is not currently claimed as implemented. Validate tool arguments in application code and consider explicit confirmation before sensitive writes.

### 4.6 SSRF through an upstream URL

**Impact:** An upstream URL could target loopback, cloud metadata, or other sensitive addresses.

**Controls:**

- URL validation requires HTTP or HTTPS.
- Validation rejects resolved addresses classified as loopback, link-local, unspecified, multicast, or reserved when an upstream is registered or its URL is updated.
- NetworkPolicy manifests provide a separate network-level control.

**Residual risk:** Registration-time URL validation cannot eliminate every SSRF scenario. DNS rebinding, redirects, changes in DNS answers, and private/internal destinations require careful treatment. NetworkPolicies only help when their rules are correct and the cluster networking implementation enforces them.

Do not claim complete SSRF protection without testing the actual application and network behaviour.

### 4.7 Credential retained after an upstream URL change

**Impact:** If a stored credential were silently reused after a URL change, it could be sent to an unintended destination.

**Controls:**

- Changing the URL of a credentialed upstream requires the credential to be entered again.
- A URL-only update was tested through the local dashboard and rejected with HTTP 422.
- The test left the original URL and Bearer-token configuration unchanged.

**Residual risk:** An administrator who knows the upstream credential can still configure a different destination and enter the credential again. URL validation and egress restrictions remain separate controls.

### 4.8 Slow or unavailable upstream

**Impact:** An unavailable server could delay discovery or prevent a chat request from completing.

**Controls:**

- Default tool-list timeout: 5 seconds.
- Default tool-call timeout: 10 seconds.
- Default tool-list cache TTL: 10 seconds.
- Failed upstreams are marked unreachable and contribute no tools to discovery.
- Other upstreams can remain available when one upstream fails.

**Observed tests:**

- Locally, disabling Utilities removed its tools from discovery; re-enabling it restored the full set of 11 tools.
- On AWS, scaling Notes to zero caused the dashboard to mark it unreachable while Utilities and WooCommerce remained connected. Restoring Notes recovered the three connected upstreams and 11 tools.

**Residual risk:** These tests cover specific upstream failures. They do not establish high availability. Failure of the gateway, EC2 instance, cluster networking, or shared storage may interrupt all gateway-mediated work.

### 4.9 Dashboard session theft and insecure transport

**Impact:** A stolen session can be used as the signed-in user. Plain HTTP may expose credentials, session data, or other traffic to a network observer.

**Controls:**

- Dashboard sessions are signed.
- Sessions have an eight-hour lifetime.
- Cookies use HttpOnly and `SameSite=Lax`.
- The cookie's secure flag is configurable.

**Residual risk:**

- Local development uses `cookieSecure: "false"`.
- The current AWS dashboard also uses HTTP without configured TLS.
- Production requires HTTPS and secure-cookie configuration.
- Review CSRF behaviour, session invalidation, and ingress access controls before public exposure.

### 4.10 Kubernetes lateral movement and service-account tokens

**Impact:** A compromised pod could try to access unrelated services, databases, or the Kubernetes API.

**Controls:**

- NetworkPolicy manifests exist in the `gateway`, `mcp-servers`, and `store` charts.
- Pod templates disable service-account-token automounting.
- Gateway, Notes, Utilities, and WooCommerce MCP are configured to run as UID 10001, with privilege escalation disabled and Linux capabilities dropped.
- WordPress and MariaDB also disable token automounting but retain their upstream image runtime users.
- The WordPress bootstrap job uses UID 33 to match file ownership.

**Residual risk:** Effective isolation depends on policy selectors, allowed traffic rules, and CNI enforcement. The existence of a NetworkPolicy does not prove every unauthorized connection is blocked. Do not claim complete isolation without observed positive and negative network tests.

NetworkPolicies do not encrypt traffic.

### 4.11 Language-model key and cost abuse

**Impact:** A leaked provider key or excessive chat usage could consume quota or incur costs.

**Controls:**

- The provider key is supplied through Kubernetes Secret configuration.
- The chat agent has a bounded tool loop.
- Individual tool results passed back to the model are size-limited.

**Residual risk:** Comprehensive per-user rate limiting and spend controls are not claimed as implemented. Use provider budgets and alerts, restrict access to Secrets, and add application-level request limits before broader deployment.

### 4.12 Database and encryption-key exposure

**Impact:** A database copy may expose account, server-registry, and audit records. A database copy together with the Fernet key could expose encrypted upstream credentials.

**Controls:**

- Passwords use Argon2 hashes.
- API keys are stored as SHA-256 hashes.
- Upstream credentials are encrypted with Fernet.
- Gateway state is stored on persistent storage.
- The gateway pod-replacement test showed previously recorded audit entries remained visible.

**Residual risk:**

- Anyone who obtains both the database and its encryption key may decrypt stored upstream credentials.
- Protect the encryption key separately from database backups.
- Define and test backup restoration.
- SQLite on a single volume is not a high-availability database.

The AWS test demonstrated persistence across a gateway pod replacement, not recovery after volume loss or database corruption.

### 4.13 Data sent to the model provider

**Impact:** Tool results may contain product, order, or customer information that is sent to the configured external model provider.

**Controls:**

- WooCommerce responses are trimmed.
- The language-model provider key is not exposed to the browser.
- The gateway controls the tool-routing path.

**Residual risk:** Returned names, order items, totals, and other data may still be sent to the provider. Avoid real customer data in the demonstration and review the provider's data-handling terms before using production records.

### 4.14 Single-node deployment and public exposure

**Impact:** A host failure, public endpoint exposure, or compromised EC2 instance could interrupt the entire service or expose its data and credentials.

**Controls and observed configuration:**

- The AWS demonstration runs on a single EC2 instance with k3s.
- Traefik provides ingress.
- Kubernetes recreates a deleted gateway pod.
- The gateway dashboard is reachable through the current nip.io hostname.

**Residual risk:**

- Pod recovery does not protect against EC2 or node failure.
- The current public gateway uses HTTP without configured TLS.
- The hostname depends on the public IP.
- A complete backup-and-restore procedure and node-level high-availability design have not been demonstrated.

Review security-group rules, ingress exposure, administrative access, storage protection, and cost controls before leaving the environment running or exposing it more broadly.

## 5. Why client keys are not forwarded upstream

A Urumi API key authenticates a user to Urumi. Forwarding that key upstream would ask another server to trust a token it did not issue, spread a gateway credential across a different trust boundary, and allow a compromised upstream to capture a token that may be usable against Urumi.

Instead, Urumi authenticates the user, enforces the user's permissions, and authenticates itself to each upstream using that upstream's own credential.

This separation limits unnecessary credential sharing and centralizes authorization and auditability.

## 6. Verification performed

The following results were observed during local testing or on the AWS demonstration deployment.

| Test | Environment | Observed result |
|---|---|---|
| Revoked API key | Local | Returned HTTP 401 |
| Member tool discovery | Local | Excluded the two default admin-only WooCommerce tools |
| Member calls admin-only tool | Local | Denied and recorded in audit activity |
| Disable and restore Utilities | Local | Its tools disappeared from and returned to discovery; the full set contained 11 tools after recovery |
| URL-only change for credentialed upstream | Local | Rejected with HTTP 422 |
| Notes upstream outage and recovery | AWS | Notes became unreachable; restoring it returned the dashboard to three connected upstreams and 11 tools |
| Gateway pod replacement | AWS | Kubernetes recreated the pod; prior audit entries remained visible |
| MariaDB pod replacement | AWS | The database pod returned and five existing WooCommerce products remained available |
| Cross-server chat | AWS | Chat called WooCommerce order retrieval and Utilities currency conversion in one request |

Source inspection also confirmed the configured non-root execution and capability restrictions for gateway, Notes, Utilities, and WooCommerce MCP, and disabled service-account-token automounting in the relevant templates. Source inspection is not a penetration test.

The currency-conversion test returned `22000` from the Utilities tool for an input amount of USD 250, and the chat displayed `22,000 INR`. This verifies the observed tool flow and response, not a live exchange rate.

Only claim additional security tests—such as specific SSRF payloads, complete NetworkPolicy-denial scenarios, TLS verification, or backup restoration—after running and observing them.

## 7. Highest-priority future work

1. Configure TLS and cert-manager, enable secure cookies, and review session and CSRF behaviour.
2. Require confirmation for consequential chat-initiated writes.
3. Consider allow-list permissions and per-user rate limits.
4. Audit management actions and define audit retention.
5. Tighten gateway egress and test NetworkPolicy enforcement.
6. Establish and test backup and restore procedures for gateway and store data.
7. Move to PostgreSQL before scaling gateway replicas.
8. Review WooCommerce authentication and forwarded-HTTPS assumptions before handling real customer data.
9. Add monitoring, alerting, provider cost controls, and operational recovery procedures.
10. Establish a repeatable image publishing and deployment pipeline and test Helm upgrades and rollbacks.

## Related documentation

- [README](../README.md)
- [System design and trade-offs](design.md)
- [AWS deployment and operations](aws-deployment.md)
