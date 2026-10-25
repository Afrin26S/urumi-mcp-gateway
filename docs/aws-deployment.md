# AWS Deployment and Operations

## 1. Overview

Urumi MCP Gateway is deployed on an AWS EC2 instance running Ubuntu 24.04 and k3s. The cluster hosts the gateway, dashboard, chat agent, WooCommerce demonstration store, and two additional MCP servers: Notes and Utilities.

The deployment is intended for demonstration and evaluation. It is a working single-node setup, not a production-hardened, highly available service.

### Deployment details

| Setting | Value |
|---|---|
| Cloud provider | AWS |
| AWS Region | `us-east-1` |
| EC2 instance name | `urumi-k3s` |
| Instance type | `t3.medium` |
| Operating system | Ubuntu 24.04 |
| Kubernetes distribution | k3s |
| Verified k3s version | `v1.36.5+k3s1` |
| Ingress controller | Traefik |
| Gateway image | `gateway:0.4.1` |
| Gateway namespace | `gateway` |
| Store namespace | `store` |
| Notes and Utilities namespace | `mcp-servers` |
| Gateway state | SQLite on a persistent volume |
| Store state | MariaDB and WordPress persistent volumes |
| Image delivery | Images imported into the k3s container runtime |
| Gateway transport | HTTP; TLS is not configured |

## 2. Accessing the deployment

### Gateway dashboard

The deployed dashboard is available at:

**http://gateway.54.235.55.63.nip.io/**

The hostname uses nip.io to resolve to the EC2 public IP address. It depends on the current public IP and may stop working if that IP changes.

The endpoint currently uses HTTP without TLS. Do not enter sensitive production credentials or use real customer data through this demonstration endpoint.

### SSH access

Connect to the EC2 instance using the SSH key configured when the instance was created. From a terminal on your own computer, the command follows this pattern:

```bash
ssh -i /path/to/your-key.pem ubuntu@54.235.55.63
```

Replace `/path/to/your-key.pem` with the actual local path to your private key.

**Never commit your private SSH key to the repository or include it in this document.**

Once connected, the shell prompt should identify the Ubuntu user and EC2 host. The application repository is located at:

```text
/home/ubuntu/urumi-mcp-gateway
```

Enter the repository directory:

```bash
cd ~/urumi-mcp-gateway
```

## 3. Kubernetes environment

The AWS environment uses k3s on the EC2 instance. Kubernetes commands are run through the k3s-managed CLI using `sudo`.

### Verify the k3s installation

```bash
sudo k3s --version
```

The verified version for this deployment is:

```text
k3s version v1.36.5+k3s1
```

### Inspect cluster nodes

```bash
sudo k3s kubectl get nodes -o wide
```

### Inspect workloads

```bash
sudo k3s kubectl get pods -A
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

The ingress command shows the actual configured hostnames. Do not assume that a store hostname exists unless it appears in the cluster output.

### Inspect persistent storage

```bash
sudo k3s kubectl get pvc -A
```

```bash
sudo k3s kubectl get pv
```

These commands inspect the running environment. They do not create or modify infrastructure.

## 4. Namespace layout

The application is divided into three Kubernetes namespaces.

| Namespace | Components |
|---|---|
| `gateway` | Urumi gateway, dashboard, management API, chat agent, and gateway state |
| `store` | WordPress, MariaDB, WooCommerce MCP, and the bootstrap job |
| `mcp-servers` | Notes and Utilities demonstration MCP servers |

To inspect a namespace:

```bash
sudo k3s kubectl get all -n gateway
```

```bash
sudo k3s kubectl get all -n store
```

```bash
sudo k3s kubectl get all -n mcp-servers
```

The `get all` command is a convenient overview, but it does not display every Kubernetes resource, such as all Secrets or persistent volume claims.

## 5. Gateway deployment and image delivery

The current AWS deployment runs the gateway image `gateway:0.4.1`.

Application images are imported into the k3s container runtime rather than pulled from Amazon Elastic Container Registry (ECR). This is the image-delivery approach used by the current demonstration deployment.

The gateway deployment can be inspected with:

```bash
sudo k3s kubectl get deployment gateway -n gateway -o wide
```

Inspect the image configured on the deployment:

```bash
sudo k3s kubectl get deployment gateway -n gateway -o jsonpath='{.spec.template.spec.containers[*].image}'
```

Check the Helm releases:

```bash
sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm list -A
```

The chart paths, values files, image tags, and overrides in the repository should be used as the source of truth when repeating a deployment. Do not assume that importing a new image automatically changes the image used by an existing Kubernetes deployment.

A repeatable image publishing and deployment pipeline has not been established by the tests documented here.

## 6. Application verification

After deployment or a recovery operation, verify that the workloads are ready.

### Check gateway readiness

```bash
sudo k3s kubectl rollout status deployment/gateway -n gateway
```

### Check pod status

```bash
sudo k3s kubectl get pods -n gateway -o wide
```

```bash
sudo k3s kubectl get pods -n store -o wide
```

```bash
sudo k3s kubectl get pods -n mcp-servers -o wide
```

### Inspect gateway logs

```bash
sudo k3s kubectl logs deployment/gateway -n gateway --tail=100
```

To follow logs continuously:

```bash
sudo k3s kubectl logs deployment/gateway -n gateway -f
```

Press `Ctrl+C` to stop following logs.

### Inspect gateway events

```bash
sudo k3s kubectl get events -n gateway --sort-by=.metadata.creationTimestamp
```

Review logs and events if a deployment does not become ready or if an upstream reports an error.

## 7. Verified AWS behaviour

The following tests were performed against the AWS deployment.

### 7.1 Upstream tool discovery

All three configured upstreams connected successfully:

| Upstream | Discovered tools |
|---|---:|
| Notes | 3 |
| Utilities | 3 |
| WooCommerce | 5 |
| **Total** | **11** |

This verified tool discovery across the three configured upstream servers.

### 7.2 Upstream failure and recovery

Notes was scaled to zero replicas to simulate an unavailable upstream.

Observed results:

- The dashboard reported Notes as unreachable.
- Notes contributed zero tools while unavailable.
- Utilities and WooCommerce remained connected.
- Restoring Notes to one replica returned the dashboard to three connected upstreams and 11 tools.

This verifies recovery from the specific Notes failure that was tested.

### 7.3 Gateway pod recovery and audit persistence

The gateway pod was deleted to test Kubernetes recovery.

Observed results:

- Kubernetes created a replacement gateway pod.
- The replacement reached the ready state.
- Previously recorded audit entries remained visible in the dashboard.

This verifies recovery after gateway pod replacement and persistence of the audit records observed during the test.

### 7.4 MariaDB pod recovery

The MariaDB pod `mariadb-0` was deleted to test recovery.

Observed results:

- Kubernetes recreated the MariaDB pod.
- WordPress and WooCommerce MCP remained running.
- The existing WooCommerce product list remained available.

Five products were returned after recovery:

- Daydream Tote Bag
- Cutesy Latte Mug ☕
- Mouse & Keyboard Set
- Premium Water Bottle
- Urumi Demo Notebook

This verifies the observed product data survived the tested pod replacement. It does not demonstrate restoration after persistent-volume loss or database corruption.

### 7.5 Cross-server chat

A chat request asked for the day's order total in rupees.

The observed tool sequence was:

1. `woocommerce__list_orders` retrieved a demonstration order with a total of USD 250.
2. `utilities__convert_currency` received the amount, source currency `USD`, and target currency `INR`.
3. Utilities returned `22000`, and the chat displayed `22,000 INR`.

This verifies that one chat request routed calls through two different upstream servers.

The conversion result was not independently verified as a live exchange rate.

## 8. Recovery and troubleshooting

### Gateway pod is not ready

Inspect the deployment and pods:

```bash
sudo k3s kubectl get deployment gateway -n gateway
```

```bash
sudo k3s kubectl get pods -n gateway -o wide
```

Inspect recent logs:

```bash
sudo k3s kubectl logs deployment/gateway -n gateway --tail=100
```

Inspect recent events:

```bash
sudo k3s kubectl get events -n gateway --sort-by=.metadata.creationTimestamp
```

Use the output to identify the cause before changing the deployment.

### An upstream is unreachable

Inspect the MCP server pods:

```bash
sudo k3s kubectl get pods -n mcp-servers -o wide
```

Inspect their logs by substituting the actual pod name:

```bash
sudo k3s kubectl logs -n mcp-servers <pod-name> --tail=100
```

Also check the gateway logs and dashboard status. An unreachable upstream may disappear from the gateway's current tool-discovery results.

### Store data is unavailable

Inspect the store workloads:

```bash
sudo k3s kubectl get pods -n store -o wide
```

Inspect the persistent volume claims:

```bash
sudo k3s kubectl get pvc -n store
```

Inspect MariaDB logs using the actual pod name:

```bash
sudo k3s kubectl logs -n store mariadb-0 --tail=100
```

Do not delete persistent volume claims or database files as a troubleshooting shortcut. Such actions may destroy data.

### Helm release inspection

```bash
sudo env KUBECONFIG=/etc/rancher/k3s/k3s.yaml helm list -A
```

This lists Helm releases and their namespaces. Use the actual release name and chart values from the repository before attempting a change.

Helm upgrade and rollback have not been claimed as verified operations for this deployment.

## 9. Persistence and backup considerations

The gateway stores state in SQLite on a persistent volume. The store uses persistent storage for MariaDB and WordPress.

The tests documented above show that selected data remained available after the gateway pod and MariaDB pod were replaced.

They do not establish:

- Recovery after EC2 instance or node failure.
- Recovery after loss or corruption of a persistent volume.
- A tested backup-and-restore procedure.
- High availability across multiple nodes.
- Safe concurrent writes from multiple gateway replicas.

Before production use, establish a backup procedure, store backups outside the single EC2 host, protect the Fernet encryption key separately, and test restoration into a clean environment.

## 10. Security limitations

The AWS deployment is a demonstration environment and currently has the following limitations:

- The gateway public endpoint uses HTTP without configured TLS.
- The hostname depends on the EC2 public IP.
- The cluster runs on one EC2 instance and is not node-level highly available.
- Images are imported into the k3s container runtime instead of being pulled from a private registry.
- Backup and restore have not been demonstrated by the tests described here.
- Helm upgrade and rollback have not been verified.
- Security-group rules, public exposure, secret handling, and cost controls require review before broader use.

Do not use real customer data or production credentials in this environment until the relevant security controls and operational procedures have been reviewed and tested.

## 11. Production-readiness work

Before treating the deployment as production-ready:

1. Configure HTTPS and certificate management.
2. Review public ingress and EC2 security-group rules.
3. Establish secure secret storage, rotation, and recovery.
4. Use a private registry and a repeatable image deployment pipeline.
5. Create and test backup-and-restore procedures.
6. Add monitoring, alerting, and resource limits.
7. Test Helm upgrade and rollback in a controlled environment.
8. Review database durability and the single-node availability boundary.
9. Add operational runbooks for incidents and recovery.

## Related documentation

- [Project README](../README.md)
- [System design and trade-offs](design.md)
- [Threat model and residual risks](threat-model.md)
