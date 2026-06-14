# Runbook — Connecting to PostgreSQL with native clients (DBeaver, psql, …)

How to reach the Traffinator database from a desktop SQL client. Two paths:

- **Port-forward** — ad-hoc, zero exposure, nothing to deploy. Use this by default.
- **LoadBalancer** — a persistent LAN endpoint (via MetalLB) for always-on access.

Assumes the chart's default `postgres.mode=cnpg` (CloudNativePG). Names follow
the chart: namespace `traffinator`, release `traffinator`, so the CNPG cluster
is `traffinator-postgres` with services `traffinator-postgres-rw` (primary, R/W),
`-ro` (replicas, read-only), `-r` (any). For `mode=bundled` see the note at the
end. Companion: [postgres-operations.md](postgres-operations.md).

```bash
export NS=traffinator CLUSTER=traffinator-postgres
```

---

## 1. Get the credentials

CloudNativePG generates the app role's password into the `<cluster>-app` Secret
(keys: `username`, `password`, `dbname`, `host`, `port`, `uri`, `jdbc-uri`):

```bash
kubectl -n "$NS" get secret "${CLUSTER}-app" -o jsonpath='{.data.username}' | base64 -d; echo
kubectl -n "$NS" get secret "${CLUSTER}-app" -o jsonpath='{.data.password}' | base64 -d; echo
kubectl -n "$NS" get secret "${CLUSTER}-app" -o jsonpath='{.data.dbname}'   | base64 -d; echo
# full connection string (handy to paste):
kubectl -n "$NS" get secret "${CLUSTER}-app" -o jsonpath='{.data.uri}'      | base64 -d; echo
```

For admin/superuser access (only if `postgres.cnpg.superuserAccess: true`), read
the `${CLUSTER}-superuser` Secret instead.

---

## 2. Ad-hoc access — `kubectl port-forward` (recommended)

No cluster changes, nothing exposed beyond your machine. The forward lives only
while the command runs.

```bash
# primary (read/write)
kubectl -n "$NS" port-forward "svc/${CLUSTER}-rw" 5432:5432
# read-only replicas instead:  svc/${CLUSTER}-ro
```

Then connect:

```bash
# psql
PGPASSWORD="$(kubectl -n "$NS" get secret ${CLUSTER}-app -o jsonpath='{.data.password}' | base64 -d)" \
  psql -h localhost -p 5432 -U commute -d commute
```

**DBeaver / pgAdmin / TablePlus** → new PostgreSQL connection:

| Field | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `commute` |
| Username | `commute` (from the `-app` secret) |
| Password | from the `-app` secret |
| SSL mode | `require` (see §4) |

---

## 3. Persistent LAN access — LoadBalancer (MetalLB)

CNPG services are `ClusterIP` by default. For an always-on endpoint, expose the
primary via a LoadBalancer (MetalLB assigns a LAN IP). Two ways:

### 3a. CNPG-native `managed.services` (recommended)
CNPG can manage an extra service that always points at the current primary
(survives failover). Add to the `Cluster` spec:

```yaml
spec:
  managed:
    services:
      additional:
        - selectorType: rw            # rw | ro | r
          serviceTemplate:
            metadata:
              name: traffinator-postgres-ext
              annotations:
                # optional fixed IP from your MetalLB pool:
                metallb.universe.tf/loadBalancerIPs: "192.168.1.50"
            spec:
              type: LoadBalancer
```

When deploying through the Helm chart this belongs on the CNPG `Cluster`
(`postgres-cnpg.yaml`); if a `postgres.cnpg.externalAccess` values toggle is
added later it will render exactly this. Get the assigned IP:

```bash
kubectl -n "$NS" get svc traffinator-postgres-ext
```

### 3b. Standalone LoadBalancer Service (alternative)
If you'd rather not touch the Cluster, create a Service that reuses the primary
selector. Copy the selector from the operator-managed `-rw` service so it stays
correct across CNPG versions:

```bash
kubectl -n "$NS" get svc "${CLUSTER}-rw" -o jsonpath='{.spec.selector}'; echo
```

```yaml
apiVersion: v1
kind: Service
metadata:
  name: traffinator-postgres-ext
  namespace: traffinator
  annotations:
    metallb.universe.tf/loadBalancerIPs: "192.168.1.50"   # optional
spec:
  type: LoadBalancer
  selector:
    # paste the selector printed above (the primary/rw selector)
    cnpg.io/cluster: traffinator-postgres
    # role: primary    # exact key/value depends on CNPG version — use what -rw uses
  ports:
    - name: postgres
      port: 5432
      targetPort: 5432
```

Point DBeaver at the LoadBalancer IP on port `5432` with the same credentials.

---

## 4. TLS

CNPG enables TLS by default with its own CA. Connect with at least
`sslmode=require` to encrypt the link:

- **DBeaver:** connection → *SSL* tab → enable SSL, SSL mode `require`.
- **psql:** `psql "host=... dbname=commute user=commute sslmode=require"`.

For full verification (`verify-full`), export CNPG's CA and point the client at
it:

```bash
kubectl -n "$NS" get secret "${CLUSTER}-ca" -o jsonpath='{.data.ca\.crt}' | base64 -d > cnpg-ca.crt
```

---

## 5. If connections are refused (`pg_hba`)

External clients connect from outside the pod network, so their source IP is the
LoadBalancer/client address. If CNPG's default `pg_hba` rejects them, add a
scoped rule (prefer your LAN CIDR over `0.0.0.0/0`) to the `Cluster` spec:

```yaml
spec:
  postgresql:
    pg_hba:
      - host all all 192.168.1.0/24 scram-sha-256
```

---

## 6. Least privilege & safety

- **Read-only tools** → connect through the `-ro` service (replicas) so a stray
  `UPDATE`/`DELETE` can't land.
- **Superuser** is off by default; enable `postgres.cnpg.superuserAccess: true`
  only when you actually need DDL/extension/role admin, and use the
  `-superuser` secret.
- A LoadBalancer puts Postgres on your LAN — keep it **off the WAN** (no router
  port-forward), restrict by source IP at MetalLB/firewall where possible, and
  rely on the strong CNPG-generated password + `sslmode=require`.
- Rotating the app password: let CNPG manage it (update the managed role) rather
  than hand-editing; clients re-read the new password from the `-app` secret.

---

## Bundled mode (`postgres.mode=bundled`)

No CNPG. The service is `traffinator-postgres` (ClusterIP) and the password is in
the chart's main Secret:

```bash
kubectl -n "$NS" get secret traffinator -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d; echo
kubectl -n "$NS" port-forward svc/traffinator-postgres 5432:5432
```

For persistent access, set `service.type` is not exposed for the bundled
Deployment — use a standalone LoadBalancer Service (§3b) selecting
`app.kubernetes.io/component: postgres` + `app.kubernetes.io/instance: traffinator`.
