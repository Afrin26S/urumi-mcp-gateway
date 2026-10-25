# Urumi MCP Gateway

**A Kubernetes-hosted MCP gateway for secure, auditable access to team tools and data sources.**

Urumi gives a team one central place to connect Model Context Protocol (MCP) servers, manage access to their tools, and use those tools through a dashboard chat agent. WooCommerce is the first business data source, supported by two demonstration MCP servers: Notes and Utilities.

Instead of giving every client direct access to every upstream server and its credentials, Urumi routes tool calls through a central gateway that handles authentication, authorization, tool discovery, and audit logging.

The project was developed locally on Windows using Docker Desktop and k3d, then deployed to an AWS EC2 instance running Ubuntu 24.04 and k3s.

**Current status:** The AWS demonstration deployment is running and has been tested for tool discovery, cross-server chat, upstream failure and recovery, gateway pod recovery, audit-log persistence, and WooCommerce data persistence after a MariaDB pod restart.

> **Important:** This is a working demonstration deployment, not a production-hardened service. The current public dashboard uses HTTP without TLS. Do not use it for sensitive production data or real customer credentials.

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Components](#components)
- [Technology stack](#technology-stack)
- [AWS deployment](#aws-deployment)
- [Verified AWS tests](#verified-aws-tests)
- [Local development](#local-development)
- [Security controls](#security-controls)
- [Operational commands](#operational-commands)
- [Known limitations and production boundary](#known-limitations-and-production-boundary)
- [Documentation](#documentation)

## Features

### Centralized MCP access

- Connect multiple upstream MCP servers through one gateway.
- Discover upstream tools and expose them through a common interface.
- Route calls to the correct upstream server.
- Keep upstream server credentials out of MCP clients.
- Support multiple tool providers, including WooCommerce, Notes, and Utilities.

### Team access and administration

- Authenticate users through the gateway.
- Apply role-based authorization to administrative and member operations.
- Associate API keys with users and validate incoming requests.
- Provide a dashboard for server management, tool discovery, chat, and audit inspection.

### Dashboard chat agent

- Let users interact with available tools through natural-language requests.
- Allow the chat agent to call tools from different upstream servers when needed.
- Return results from tool execution in the chat interface.

### Auditing and resilience

- Record tool and gateway activity for inspection.
- Use timeouts when listing tools and executing upstream calls.
- Detect upstream connection failures.
- Allow Kubernetes to recreate failed pods.
- Persist gateway audit records and store data beyond the lifetime of an individual pod, subject to the current storage configuration.

## Architecture

```text
                         Team members / administrators
                                      |
                                      v
                           Dashboard + Chat Agent
                                      |
                                      v
                              Urumi MCP Gateway
                         Authentication / Authorization
                           Tool routing / Audit logging
                                      |
                    +-----------------+-----------------+
                    |                 |                 |
                    v                 v                 v
              WooCommerce           Notes            Utilities
               MCP server         MCP server         MCP server
                    |                 |                 |
                    v                 v                 v
              WordPress +       Demonstration       Currency and
                MariaDB          search tools       utility tools

                         Kubernetes: k3s on AWS EC2
```

The diagram represents the logical architecture. The application components run in separate Kubernetes namespaces on the current single-node EC2 cluster.

### Request flow

1. A user accesses the dashboard or sends a request to the gateway.
2. The gateway authenticates the request and checks the relevant permissions.
3. The gateway discovers or routes to the appropriate upstream MCP tool.
4. The selected upstream executes the operation and returns its result.
5. The gateway returns the result to the client and records relevant activity for audit inspection.

For a cross-server request, the chat agent may invoke more than one upstream tool before responding.

## Components

| Component | Purpose | Image / namespace |
|---|---|---|
| Urumi Gateway | MCP endpoint, management API, dashboard, chat agent, and audit log | `gateway:0.4.1` / `gateway` |
| WooCommerce MCP | Exposes store operations through MCP tools | `woocommerce-mcp:0.1.0` / `store` |
| Notes MCP | Demonstration upstream with search functionality | `demo-mcp:0.1.0` / `mcp-servers` |
| Utilities MCP | Demonstration utility tools, including currency conversion | `demo-mcp:0.1.0` / `mcp-servers` |
| WordPress | Store application and WooCommerce interface | `wordpress:7-apache` / `store` |
| MariaDB | Persistent store database | `mariadb:11.4` / `store` |

The demonstration servers share the `demo-mcp:0.1.0` image tag in this deployment. Their configured tools and runtime instances are separate.

## Technology stack

| Area | Technology |
|---|---|
| Backend and MCP | Python, MCP SDK, FastAPI |
| Frontend | React, Vite |
| Containerization | Docker |
| Orchestration | Kubernetes with k3s |
| Packaging | Helm |
| Store integration | WordPress, WooCommerce, MariaDB |
| Gateway persistence | SQLite on a persistent volume |
| Cloud hosting | AWS EC2 |
| Ingress | Traefik |
| Source control | Git and GitHub |

## AWS deployment

Urumi is deployed on an AWS EC2 instance running Ubuntu 24.04 and k3s.

### Deployment configuration

| Setting | Current deployment |
|---|---|
| Cloud provider | AWS |
| Region | `us-east-1` |
| EC2 instance type | `t3.medium` |
| Operating system | Ubuntu 24.04 |
| Kubernetes distribution | k3s |
| k3s version | `v1.36.5+k3s1` |
| Ingress controller | Traefik |
| Gateway image | `gateway:0.4.1` |
| Gateway namespace | `gateway` |
| Store namespace | `store` |
| Demo upstream namespace | `mcp-servers` |
| Gateway persistence | SQLite backed by a persistent volume |
| Store persistence | MariaDB and WordPress persistent volumes |
| Container image delivery | Images imported into the k3s container runtime |
| Public gateway transport | HTTP; TLS is not configured |

### Live dashboard

**[Open the Urumi Gateway Dashboard](http://gateway.54.235.55.63.nip.io/)**

The current gateway hostname is:

`gateway.54.235.55.63.nip.io`

This hostname uses nip.io to resolve to the EC2 public IP. It depends on the current IP address and may stop working if that address changes. The deployment currently uses HTTP rather than HTTPS.

### Kubernetes namespaces

- `gateway` — Urumi gateway and its persistent data.
- `store` — WordPress, WooCommerce MCP, MariaDB, and related workloads.
- `mcp-servers` — Notes and Utilities demonstration MCP servers.

### Accessing the cluster

Connect to the EC2 instance over SSH using your configured SSH key, then use the k3s-managed Kubernetes CLI.

Check the Kubernetes version:

```bash
sudo k3s --version
```

List the cluster nodes:

```bash
sudo k3s kubectl get nodes -o wide
```

List workloads across namespaces:

```bash
sudo k3s kubectl get pods -A
```

Inspect the ingress configuration:

```bash
sudo k3s kubectl get ingress -A -o wide
```

Inspect the gateway deployment:

```bash
sudo k3s kubectl get deployment -n gateway
```

Check persistent volume claims:

```bash
sudo k3s kubectl get pvc -A
```

These commands inspect the existing deployment; they do not create or modify infrastructure.

### Image delivery and deployment approach

Application images are imported into the k3s container runtime for this demonstration. The current setup does not rely on Amazon Elastic Container Registry (ECR) to pull these images.

Helm is used to manage the Kubernetes application configuration. Because the cluster is administered through k3s, the Helm command may need the k3s kubeconfig explicitly:

```bash
sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm list -A
```

The exact chart paths and deployment-specific values should be taken from the checked-in Helm charts and the configuration used for the current installation. Do not assume that rebuilding or importing an image automatically updates a running deployment; the workload must be updated through its configured deployment process.

## Verified AWS tests

The following behaviours were exercised against the deployed AWS environment.

### 1. All three upstream MCP servers connected

The dashboard showed the following tool counts:

| Upstream | Tools |
|---|---:|
| Notes | 3 |
| Utilities | 3 |
| WooCommerce | 5 |
| **Total** | **11** |

This verifies that the gateway could connect to the three configured upstream servers and discover their tools.

### 2. Cross-server chat and tool routing

A request asked the chat agent for the day's order total in rupees.

The observed tool sequence was:

1. `woocommerce__list_orders` retrieved a demo order with a total of USD 250.
2. `utilities__convert_currency` was called with `amount: 250`, `from_currency: "USD"`, and `to_currency: "INR"`.
3. The Utilities tool returned `22000`, and the chat agent presented the result as **₹22,000**.

This demonstrates a request that used both the WooCommerce and Utilities upstreams.

The returned conversion is the result of the configured Utilities tool. It was not independently verified as a live foreign-exchange rate.

### 3. Upstream failure and recovery

Notes was scaled down to zero replicas to simulate an unavailable upstream.

Observed behaviour:

- The dashboard reported Notes as unreachable.
- Notes exposed zero available tools while unavailable.
- Utilities and WooCommerce remained connected.
- Restoring Notes to one replica returned the dashboard to three connected upstreams and 11 tools.

This verifies the tested failure and recovery behaviour for Notes.

### 4. Gateway pod recovery and audit persistence

The gateway pod was deleted to test Kubernetes recovery.

Observed behaviour:

- Kubernetes created a replacement gateway pod.
- The replacement pod reached the `Running` and ready state.
- Previously recorded audit entries were still visible in the dashboard.

This verifies recovery after gateway pod replacement and persistence of the audit records observed in the test.

### 5. Store database pod recovery and data persistence

The MariaDB pod `mariadb-0` was deleted to test pod recovery.

Observed behaviour:

- Kubernetes recreated the MariaDB pod.
- WordPress and WooCommerce MCP remained running.
- The existing WooCommerce product list was still available after recovery.

The test returned five products:

| Product | Demo price |
|---|---:|
| Daydream Tote Bag | 350 |
| Cutesy Latte Mug ☕ | 250 |
| Mouse & Keyboard Set | 699 |
| Premium Water Bottle | 399 |
| Urumi Demo Notebook | 199 |

These are demonstration store values; the currency and formatting depend on the configured WooCommerce store.

### 6. Order retrieval

The `woocommerce__list_orders` tool successfully retrieved a demo order, including its order ID, status, source currency, amount, and line item.

This verifies that the gateway could route an order retrieval request to the WooCommerce upstream and return the result to the chat agent.

### What these tests establish

The tests establish that the deployed demonstration can discover tools, route calls across upstream servers, respond to a tested upstream outage, recover Kubernetes-managed pods, and retain the specific data checked after pod replacement.

They do **not** establish high availability, disaster recovery, backup restoration, resistance to every security threat, production scalability, or uninterrupted public availability.

## Local development

The project was developed on Windows using Docker Desktop, Git, k3d, kubectl, and Helm.

### Prerequisites

Install and configure:

- Git
- Docker Desktop
- kubectl
- k3d
- Helm
- Python, for the backend and MCP services
- Node.js and npm, for the frontend

The precise Python and Node.js versions should match the requirements in the relevant project files.

### Clone the repository

```bash
git clone https://github.com/Afrin26S/urumi-mcp-gateway.git
cd urumi-mcp-gateway
```

### Inspect the repository

```bash
git status
```

Review the project structure and its setup instructions before starting services. In particular, check the frontend, gateway service, MCP server implementations, Helm charts, and configuration files.

### Local Kubernetes environment

The local development environment uses Docker Desktop and k3d. The `urumi` cluster was used for local testing.

Check whether the cluster exists:

```bash
k3d cluster list
```

Inspect the Kubernetes context:

```bash
kubectl config current-context
```

If the `urumi` cluster has already been created and is running, inspect its workloads with:

```bash
kubectl get pods -A
```

Do not recreate an existing cluster or delete persistent volumes unless you intend to reset the environment.

### Configuration and secrets

Use the configuration templates and instructions included in the repository. Supply local secrets through environment variables, Kubernetes Secrets, or the documented development setup.

Do not commit:

- `.env` files containing real credentials
- API keys, access tokens, or passwords
- Private SSH keys
- Database dumps containing sensitive data
- Production secrets or encryption keys

The local environment and AWS deployment have different network addresses and configuration. Do not copy local endpoint URLs into the AWS configuration without checking the target environment.

## Security controls

The gateway implementation includes security controls intended to reduce the risk of unauthorized access and unsafe upstream calls. These describe implementation-level protections and should not be interpreted as proof that every control has undergone an independent security audit.

The implementation includes:

- **Authentication:** User authentication and signed, HTTP-only session cookies.
- **Password storage:** Argon2 password hashing.
- **API key handling:** SHA-256 hashes for stored API keys and user-associated key ownership.
- **Authorization:** Role-based checks for administrative and member operations.
- **Upstream credentials:** Fernet-based encryption for stored upstream credentials.
- **Auditability:** Audit records for relevant gateway activity.
- **Timeouts:** Separate timeout limits for upstream tool listing and tool execution.
- **Caching:** A short-lived tool-listing cache to reduce repeated discovery requests.
- **Upstream URL validation:** Validation intended to block unsafe destinations, including loopback, link-local, unspecified, multicast, and reserved addresses.
- **Login throttling:** A limit after repeated failed login attempts.
- **Kubernetes hardening:** Deployment configuration includes non-root execution, dropped Linux capabilities, disabled service-account token automounting, and NetworkPolicy templates.

These protections do not eliminate all risk. In particular, URL validation alone does not guarantee protection against every SSRF scenario, and NetworkPolicy templates only provide protection when they are correctly applied and supported by the cluster networking configuration.

## Operational commands

Run the following commands on the EC2 instance over SSH.

### Inspect pods

```bash
sudo k3s kubectl get pods -A -o wide
```

### Inspect deployments

```bash
sudo k3s kubectl get deployments -A
```

### Inspect services and ingress

```bash
sudo k3s kubectl get svc -A
```

```bash
sudo k3s kubectl get ingress -A -o wide
```

### Check gateway logs

```bash
sudo k3s kubectl logs -n gateway deployment/gateway --tail=100
```

To follow the logs live:

```bash
sudo k3s kubectl logs -n gateway deployment/gateway -f
```

Press `Ctrl+C` to stop following the logs.

### Check gateway events

```bash
sudo k3s kubectl get events -n gateway --sort-by=.metadata.creationTimestamp
```

### Inspect persistent storage

```bash
sudo k3s kubectl get pvc -A
```

```bash
sudo k3s kubectl get pv
```

### Check Helm releases

```bash
sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm list -A
```

### Check the gateway rollout

```bash
sudo k3s kubectl rollout status deployment/gateway -n gateway
```

These commands are for observation and troubleshooting. Deleting pods, changing replica counts, modifying secrets, or applying Helm changes can affect the live deployment and should be done deliberately.

## Known limitations and production boundary

The current AWS environment is a demonstration deployment with a single EC2 host. The following limitations remain relevant.

### Transport and public exposure

- The dashboard is accessible through an HTTP nip.io hostname.
- TLS has not been configured for the current public endpoint.
- The hostname depends on the instance's public IP.
- Public ingress, firewall rules, and access restrictions must be reviewed before exposing the service more broadly.

### Availability and persistence

- The Kubernetes cluster is hosted on a single EC2 instance.
- Pod recreation is not equivalent to node-level high availability.
- Persistent volumes are associated with the single-node environment.
- Pod-replacement persistence was tested, but a complete backup-and-restore procedure has not been demonstrated by the tests listed here.
- The gateway uses SQLite on persistent storage and is intended to run as a single replica in this deployment.

### Images and releases

- The current demonstration uses images imported into the k3s container runtime rather than a private image registry.
- A repeatable image publishing and deployment pipeline has not been established by the deployment tests described here.
- Helm upgrade and rollback have not been claimed as verified tests.

### Secrets and operations

- Secrets and encryption keys must be managed carefully and must not be committed to Git.
- Production deployment would require a documented secret-rotation and recovery process.
- Resource limits, monitoring, backups, incident response, and ongoing cost controls need further review.
- The demo WooCommerce data and test credentials must not be treated as production data.

### Before production use

A production-oriented deployment should, at minimum:

1. Configure HTTPS and validate certificate renewal.
2. Review ingress exposure, security-group rules, and administrative access.
3. Use a secure image registry and a repeatable deployment pipeline.
4. Establish and test backup restoration for SQLite and store data.
5. Define secret storage, rotation, and recovery procedures.
6. Add monitoring, alerting, resource limits, and operational runbooks.
7. Test upgrade and rollback procedures in a controlled environment.
8. Perform a security review against the actual deployed configuration.

## Documentation

- [System design and trade-offs](docs/design.md)
- [Threat model and residual risks](docs/threat-model.md)
- [AWS deployment and operations](docs/aws-deployment.md)

The design document explains the architecture and major decisions. The threat model documents security assumptions and residual risks. The AWS deployment document should contain the deployment-specific configuration, verification steps, and operational procedures for the current EC2 environment.

## Project goal

Urumi aims to make MCP-based tools easier for a team to operate through a single gateway, while centralizing access control, upstream integration, and auditability.

The current AWS deployment demonstrates the core workflow with WooCommerce, Notes, and Utilities. Further work is needed before treating the service as production-ready.
