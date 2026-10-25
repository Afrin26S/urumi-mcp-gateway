# Urumi MCP Gateway

Urumi is a team MCP gateway on Kubernetes, with WooCommerce as its first data source. An administrator registers upstream MCP servers once; team members use permitted tools through one MCP endpoint or the dashboard chat agent. The gateway owns authentication, authorization, routing, and auditing. Clients do not receive upstream credentials.

This repository demonstrates the system on a local k3d cluster. It is not a claim that a public production deployment is complete.

- [System design and trade-offs](docs/design.md)
- [Threat model and residual risks](docs/threat-model.md)

## Architecture

```text
MCP client (Inspector / compatible client)        Dashboard (React) + chat agent
       | Authorization: Bearer <user API key>               | session cookie
       +-------------------------------+---------------------+
                                       v
                            Gateway (namespace: gateway)
                     /mcp, /api, auth, permissions, routing,
                           timeouts, audit, chat agent
                                       |
                 +---------------------+--------------------+
                 |                     |                    |
          woocommerce-mcp           notes-mcp          utilities-mcp
             (store)             (mcp-servers)         (mcp-servers)
                 |                     |                    |
          WooCommerce REST          demo tools            demo tools
                 |
          WordPress + WooCommerce
                 |
              MariaDB
```

Tools are named `server__tool`, for example `woocommerce__list_orders`, `notes__search`, and `utilities__convert_currency`. Prefixing tools avoids collisions between upstreams.

## Components

| Component | Purpose | Image / namespace |
|---|---|---|
| Store | WordPress, WooCommerce, MariaDB | `wordpress:7-apache`, `mariadb:11.4`; `store` |
| WooCommerce MCP | Five store tools over WooCommerce REST API | `woocommerce-mcp:0.1.0`; `store` |
| Demo MCP servers | Notes and Utilities for routing/auth/failure tests | `demo-mcp:0.1.0`; `mcp-servers` |
| Gateway | MCP endpoint, management API, React dashboard, chat agent | `gateway:0.4.0`; `gateway` |

All three enabled upstreams expose 11 admin-visible tools in the local configuration: Notes (3), Utilities (3), and WooCommerce (5). Members see 9 because `woocommerce__create_product` and `woocommerce__update_order_status` are admin-only.

## Repository layout

- `charts/store/` â€” WordPress, WooCommerce, MariaDB, WooCommerce MCP, bootstrap job, NetworkPolicies.
- `charts/demo-mcp/` â€” Notes and Utilities deployments and NetworkPolicies.
- `charts/gateway/` â€” gateway deployment and NetworkPolicies.
- `services/woocommerce-mcp/` â€” WooCommerce MCP server.
- `services/demo-mcp/` â€” Notes and Utilities MCP servers.
- `services/gateway/` â€” routing, management API, chat agent, security helpers, SQLite schema, smoke test, and dashboard source.
- `scripts/dev.ps1` â€” local cluster start/stop/status helper.
- `docs/` â€” design decisions and threat model.

## Prerequisites

The local workflow uses Windows PowerShell, Docker Desktop, k3d, `kubectl`, Helm, Git, and Python for the optional smoke test. Node/npm is only needed when developing the frontend separately; the gateway Docker build packages the dashboard.

Stop XAMPP Apache, IIS, or another local service using host port 80 before starting the cluster.

## Local setup

The following commands describe a fresh installation. If the `urumi` cluster or any Secret already exists, skip that creation step instead of recreating it.

### 1. Start the cluster

From the repository root:

```powershell
.\scripts\dev.ps1 -Action start
```

This checks Docker, detects an Apache `httpd` process that may own port 80, starts the `urumi` cluster, waits for Kubernetes to respond, and waits for workloads in `store`, `mcp-servers`, and `gateway`.

Other actions:

```powershell
.\scripts\dev.ps1 -Action status
.\scripts\dev.ps1 -Action stop
```

`stop` stops the cluster without deleting it. For a fresh environment, the equivalent cluster-creation command is:

```powershell
k3d cluster create urumi --agents 1 -p "80:80@loadbalancer" -p "443:443@loadbalancer"
```

Do not run that if the `urumi` cluster already exists.

### 2. Create namespaces

```powershell
kubectl create namespace store
kubectl create namespace mcp-servers
kubectl create namespace gateway
```

If a namespace already exists, continue rather than deleting it.

### 3. Create required Secrets

Do not commit secret values or paste them into chat. These key names are confirmed by the current chart templates. On an already-running cluster, inspect existing secrets first and do not replace them casually.

```powershell
function New-Pass {
    $b = New-Object byte[] 18
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    [Convert]::ToBase64String($b).Replace('+','A').Replace('/','B')
}
function New-Hex($n) {
    $b = New-Object byte[] $n
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    -join ($b | ForEach-Object { $_.ToString("x2") })
}
function New-FernetKey {
    $b = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    [Convert]::ToBase64String($b).Replace('+','-').Replace('/','_')
}

$secure = Read-Host "Choose the gateway admin password" -AsSecureString
$adminPassword = [System.Net.NetworkCredential]::new("", $secure).Password
$utilitiesToken = New-Hex 24
$rootPassword = New-Pass
$dbPassword = New-Pass
$wpPassword = New-Pass
$consumerKey = "ck_$(New-Hex 20)"
$consumerSecret = "cs_$(New-Hex 20)"

kubectl create secret generic store-secrets -n store `
  "--from-literal=mariadb-root-password=$rootPassword" `
  "--from-literal=mariadb-password=$dbPassword" `
  "--from-literal=wp-admin-password=$wpPassword"

kubectl create secret generic woocommerce-api -n store `
  "--from-literal=consumer-key=$consumerKey" `
  "--from-literal=consumer-secret=$consumerSecret"

kubectl create secret generic utilities-token -n mcp-servers `
  "--from-literal=token=$utilitiesToken"

kubectl create secret generic gateway-secrets -n gateway `
  "--from-literal=encryption-key=$(New-FernetKey)" `
  "--from-literal=jwt-secret=$(New-Hex 32)" `
  "--from-literal=admin-password=$adminPassword" `
  "--from-literal=utilities-token=$utilitiesToken"
```

For the dashboard chat agent, create the LLM secret only when configuring a provider:

```powershell
$secureLlm = Read-Host "LLM provider API key" -AsSecureString
$llmKey = [System.Net.NetworkCredential]::new("", $secureLlm).Password
kubectl create secret generic llm-credentials -n gateway "--from-literal=api-key=$llmKey"
$llmKey = $null
```

The gateway chart expects `api-key` in `llm-credentials`. Protect the Fernet key separately from database backups; losing the key makes stored upstream credentials unreadable. These are local-demo instructions, not a complete production secret-management design.

| Secret | Namespace | Keys |
|---|---|---|
| `store-secrets` | `store` | `mariadb-root-password`, `mariadb-password`, `wp-admin-password` |
| `woocommerce-api` | `store` | `consumer-key`, `consumer-secret` |
| `utilities-token` | `mcp-servers` | `token` |
| `gateway-secrets` | `gateway` | `encryption-key`, `jwt-secret`, `admin-password`, `utilities-token` |
| `llm-credentials` | `gateway` | `api-key` |

### 4. Build and import images

```powershell
docker build -t woocommerce-mcp:0.1.0 .\services\woocommerce-mcp
docker build -t demo-mcp:0.1.0 .\services\demo-mcp
docker build -t gateway:0.4.0 .\services\gateway
k3d image import woocommerce-mcp:0.1.0 demo-mcp:0.1.0 gateway:0.4.0 -c urumi
```

### 5. Install the charts

```powershell
helm upgrade --install store .\charts\store -n store --create-namespace -f .\charts\store\values-local.yaml
helm upgrade --install demo-mcp .\charts\demo-mcp -n mcp-servers --create-namespace
helm upgrade --install gateway .\charts\gateway -n gateway --create-namespace -f .\charts\gateway\values-local.yaml
kubectl get pods -A
kubectl get networkpolicy -A
```

The first store install can take a few minutes because a bootstrap job configures WordPress/WooCommerce and the API integration. Long-running workloads should become ready; the bootstrap pod should finish with `Completed`.

### 6. Open the application

- Storefront: <http://store.localtest.me>
- Gateway dashboard: <http://gateway.localtest.me>
- API docs: <http://gateway.localtest.me/api/docs>
- MCP endpoint: `http://gateway.localtest.me/mcp`

The example admin email is `admin@example.com`. Use the password configured for this cluster; do not assume a default password.

`*.localtest.me` normally resolves to loopback, so a hosts-file edit is usually unnecessary. k3d maps host ports 80 and 443 to the load balancer, which forwards traffic to Traefik.

## AWS deployment (EC2 + k3s)

This is the planned AWS deployment path; it is not evidence of a completed
public deployment. The local Windows/k3d workflow remains the development
environment. The AWS target is an Ubuntu EC2 instance running k3s, with
container images stored in private Amazon ECR repositories and workloads
installed using the existing Helm charts.

### Deployment architecture

- **Compute:** Ubuntu EC2 instance running k3s and Traefik.
- **Container registry:** Private ECR repositories for `gateway`,
  `demo-mcp`, and `woocommerce-mcp`.
- **Workloads:** `store`, `demo-mcp`, and `gateway` Helm releases in their
  respective namespaces.
- **State:** Persistent volumes for gateway SQLite, WordPress, and MariaDB.
- **External access:** A domain and tested TLS configuration before exposing
  the dashboard or store publicly.

### Before provisioning AWS resources

1. Confirm the AWS account, region, available credits, and budget alerts.
2. Choose an EC2 instance size that can run WordPress, MariaDB, k3s, and all
   MCP services together. Validate actual resource use before increasing load.
3. Create private ECR repositories and push versioned images. Configure the
   instance to authenticate to ECR using an appropriate IAM role; do not put
   AWS access keys in the repository or container images.
4. Generate fresh production secrets. Do not reuse local-demo passwords,
   API tokens, encryption keys, or database credentials.
5. Configure persistent storage and a backup/restore plan. Keep the gateway
   Fernet encryption key backed up separately and securely.
6. Configure DNS and complete the Ingress TLS/cert-manager work. The current
   Ingress templates define HTTP routing but do not provision a complete TLS
   setup. Do not expose the dashboard publicly until HTTPS and secure cookies
   have been tested.

### Deployment order

1. Provision the EC2 instance, restrict inbound security-group rules, and
   install and secure k3s.
2. Configure private ECR access and build/push the three application images
   with immutable version tags or digests.
3. Create the `store`, `mcp-servers`, and `gateway` namespaces and provision
   the required Secrets in their correct namespaces.
4. Configure the production Helm values with registry-qualified image
   references, the real gateway hostname, and the intended LLM provider.
5. Install or upgrade the `store` chart, then `demo-mcp`, then `gateway`.
   Verify the WordPress bootstrap job completes and all expected pods become
   ready before testing the gateway.
6. Verify the storefront, gateway health endpoint, dashboard login, MCP
   authentication, all three upstreams, audit events, and Metrics.
7. Configure and verify TLS, HTTPS-only cookies, backups, and recovery
   procedures before permitting public access.

### Production deployment gates

- The gateway uses SQLite on a ReadWriteOnce volume and must remain a
  single replica. Do not scale it horizontally without moving state to a
  shared database and testing migrations.
- Confirm the storage provisioner, reclaim policy, backup schedule, and
  restore process. Persistent volumes alone are not backups.
- Keep database credentials, gateway signing/encryption keys, upstream
  tokens, and LLM API keys out of Git, shell history, logs, and public output.
- Verify NetworkPolicies against the actual k3s networking configuration;
  the presence of policy objects alone does not prove isolation.
- Review WooCommerce forwarded-HTTPS assumptions, provider data handling,
  request-rate controls, audit retention, and cost alerts before using real
  customer data.
- The `values-prod.yaml` files are starting examples, not ready-to-deploy
  production configurations. The AWS deployment is complete only after the
  actual environment passes its deployment and security checks.
## Using Urumi

### Dashboard chat

Example prompts:
- â€œWhat orders came in today?â€
- â€œCreate a product called Test Notebook with a price of 199.â€
- â€œWhat is the total of today's orders in rupees?â€

The last prompt can require WooCommerce and Utilities in the same turn. Inspect the tool trace and structured results when validating totals; the model's natural-language summary can be inaccurate even when a tool returned the correct value.

### External MCP client

Create an API key in the dashboard and copy it when shown. Configure a compatible MCP client with:

- URL: `http://gateway.localtest.me/mcp`
- Header: `Authorization: Bearer <your-api-key>`

MCP Inspector can list and call tools, but does not itself provide a model for natural-language orchestration. Use a model-enabled client to test prompt-driven multi-tool orchestration outside the dashboard.

Treat the API key like a password. Revoke it when no longer needed. Do not expose the local HTTP endpoint publicly.

## Smoke test

The smoke test reads `GATEWAY_KEY` and `GATEWAY_URL`. In PowerShell:

```powershell
cd .\services\gateway
$env:GATEWAY_URL = "http://gateway.localtest.me/mcp"
$secureKey = Read-Host "Enter an active gateway API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
    $env:GATEWAY_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
python smoke_test.py
Remove-Item Env:GATEWAY_KEY
```

The script defaults to `http://127.0.0.1:8300/mcp`; set `GATEWAY_URL` to test through ingress. A `401` from `/mcp` without a key is expected and confirms the request reached the gateway.

### Verified local results

- All enabled upstreams expose 11 admin-visible tools: 3 Notes, 3 Utilities, and 5 WooCommerce.
- With Utilities disabled, discovery returned the remaining 8 tools; re-enabling it restored all 11.
- A revoked API key returned HTTP 401.
- The admin Metrics page displayed per-upstream call counts, successes, failures, denied calls, error rates, average latency, p95 latency, and connection status from the audit log.
- Updating a credentialed upstream's URL without re-entering its credential was rejected with HTTP 422; the original URL and Bearer-token configuration remained unchanged.
- When Notes was scaled to zero, the dashboard reported it unreachable while Utilities and WooCommerce remained connected; restoring Notes recovered it.
- A member key discovered/called member-permitted tools, and an admin-only write tool was denied to a member and logged.
- A dashboard chat turn used WooCommerce and Utilities in the same turn for order lookup and currency conversion. A displayed natural-language total did not match the tool's numeric result, so verify important calculations against structured tool output.

## Security controls and limitations

Implemented controls include Argon2 password hashing; SHA-256 hashes for random API keys; signed HttpOnly dashboard sessions with an eight-hour lifetime; per-user key ownership checks; admin/member authorization; admin-only tool filtering and call-time enforcement; Fernet encryption of upstream credentials; audit records for tool outcomes; 5-second list and 10-second call timeouts; a 10-second listing cache; upstream URL validation against loopback, link-local, unspecified, multicast, and reserved addresses; and login throttling after five failures in ten minutes.

NetworkPolicy templates exist in the store, demo MCP, and gateway charts. Service-account-token automounting is disabled in the pod templates. Gateway, Notes, Utilities, and WooCommerce MCP are configured as non-root (UID 10001), with privilege escalation disabled and Linux capabilities dropped. WordPress and MariaDB also disable service-account token automounting, but retain the runtime users configured by their upstream images.

These controls do not make the demo safe for unrestricted public exposure. Changing the URL of a credentialed server requires entering its credential again, and this behavior was verified locally. Administrators who know an upstream credential can still configure that upstream URL, so URL validation and network egress restrictions remain important.

## Production boundary

The `values-prod.yaml` files are starting examples, not ready-to-deploy production configs. Before public exposure:

1. Configure real DNS and add/test TLS and cert-manager settings in the ingress templates; the current templates do not provision a complete certificate setup.
2. Set `cookieSecure: "true"` when serving the dashboard exclusively through HTTPS.
3. Use a registry and immutable image tags/digests.
4. Provision Secrets safely and restrict Kubernetes access.
5. Choose an appropriate storage class and test backup/restore.
6. Do not scale SQLite-backed gateway replicas horizontally without moving state to a shared database such as PostgreSQL.
7. Add provider-cost controls, rate limits, monitoring, audit retention, and security regression tests.
8. Review the WooCommerce forwarded-HTTPS assumptions before handling real data.

A VPS deployment, multi-store provisioning, OAuth authorization, and a multi-replica gateway are not claimed as completed.

## Troubleshooting

**Smoke test reports `ConnectError: All connection attempts failed`**

```powershell
$env:GATEWAY_URL = "http://gateway.localtest.me/mcp"
curl.exe -i http://gateway.localtest.me/api/docs
curl.exe -i http://gateway.localtest.me/mcp
```

A `401` on `/mcp` without a key is expected.

**An upstream is unreachable**

```powershell
kubectl get pods -A
kubectl logs deployment/gateway -n gateway
kubectl get networkpolicy -A
```

Check the upstream pod, dashboard error, and policy selectors before changing configuration.

**Port 80 is busy**

Stop XAMPP Apache/IIS or another process using port 80, then run `.\scripts\dev.ps1 -Action start`.

## Repository hygiene

Do not commit `.env` files, database files (`*.db`), provider keys, test output containing credentials, `node_modules`, generated `dist`, or temporary backups. The `values-local.yaml` file may be committed only after verifying that it contains no credentials or other secrets. Check `git status --short` and stage explicit filenames rather than blindly staging the whole repository.
