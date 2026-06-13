# Runbook — PostgreSQL operations (L7)

Operational runbook for the Traffinator database, run on Kubernetes via the
**CloudNativePG (CNPG)** operator: connecting, dumps, restoring into a different
schema, logical replication (to migrate to Aurora or another managed Postgres),
pgAudit auditing shipped through the existing log pipeline, and metrics /
query-performance monitoring in Grafana.

**Why CNPG (not a hand-rolled Deployment):** it's the idiomatic Kubernetes way —
the operator manages failover, backups, replicas, and metrics declaratively, and
its operand images already bundle `pgaudit`, `pg_stat_statements`, and the
contrib modules we use (`cube`, `earthdistance`). No custom image to maintain.

> **Status:** the Traffinator Helm chart currently ships a plain Postgres
> Deployment. Migrating it to a CNPG `Cluster` (and installing the operator) is
> done in the **ArgoCD/operator session** (separate). This runbook is written
> CNPG-first so it's the target reference; the dump/restore/replication
> mechanics apply to any Postgres, the CNPG-specific bits are called out.

Helper scripts live in [`scripts/`](scripts/): `db-env.sh` (shared, CNPG-aware),
`db-dump.sh`, `db-restore-to-schema.sh`. For the table/column reference and ER
diagrams, see [../database-schema.md](../database-schema.md).

---

## Homelab integration (github.com/mattyo161/homelab)

Plug into what already runs — don't add parallel infrastructure:

| Capability | Already running | How this runbook uses it |
|---|---|---|
| **Logs** | **Vector** DaemonSet → **Loki** + **BetterStack Logs** | pgAudit logs to stdout → picked up automatically (§7). |
| **Metrics** | **kube-prometheus-stack** (Grafana `grafana.oue.home`, Loki datasource) | CNPG's built-in exporter + a `PodMonitor`; dashboards in existing Grafana (§8). |
| **Storage** | **Longhorn** (`storageClass: longhorn`, 2 replicas) | CNPG cluster storage + CSI VolumeSnapshot backups. |
| **Ingress/TLS** | Traefik + cert-manager (`selfsigned-cluster-issuer`), `*.oue.home` | App ingress → `traffinator.oue.home`. |
| **GitOps** | **ArgoCD** app-of-apps | Install CNPG operator + Cluster as Applications (separate session). |
| **BetterStack** | Vector→Logs; uptime heartbeats; creds in `betterstack-credentials` | Logs flow today; **metrics → BetterStack deferred** until Grafana is working. |

---

## 0. Prerequisites

```bash
export NS=traffinator CLUSTER=traffinator-db PG_DB=commute
```
Optional but very handy — the CNPG kubectl plugin:
```bash
kubectl krew install cnpg          # then: kubectl cnpg status traffinator-db -n traffinator
```

---

## 1. Connect to the database

CNPG creates three services and two secrets:
- Services: `${CLUSTER}-rw` (primary, read/write), `${CLUSTER}-ro` (replicas),
  `${CLUSTER}-r` (any).
- Secrets: `${CLUSTER}-app` (app user/db) and `${CLUSTER}-superuser` (only if
  `enableSuperuserAccess: true`). Each holds `username`, `password`, `dbname`,
  `host`, `port`, `uri`.

### 1a. psql via the CNPG plugin (simplest)
```bash
kubectl cnpg psql "$CLUSTER" -n "$NS"          # as superuser on the primary
kubectl cnpg psql "$CLUSTER" -n "$NS" -- -d commute
```

### 1b. psql by exec-ing the primary pod (no plugin)
```bash
source docs/runbooks/scripts/db-env.sh
kubectl -n "$NS" exec -it "$(pg_pod)" -- \
  env PGPASSWORD="$(pg_password)" psql -U "$PG_USER" -d "$PG_DB"
```

### 1c. Port-forward for a local client (DBeaver/psql)
```bash
kubectl -n "$NS" port-forward "svc/${CLUSTER}-rw" 5432:5432
PGPASSWORD="$(kubectl -n "$NS" get secret "${CLUSTER}-app" -o jsonpath='{.data.password}' | base64 -d)" \
  psql -h localhost -U "$(kubectl -n "$NS" get secret "${CLUSTER}-app" -o jsonpath='{.data.username}' | base64 -d)" -d commute
```

### 1d. Orient yourself
```sql
\l                 -- databases
\dn                -- schemas
\dt                -- tables
\di+               -- indexes (note the GiST earthdistance ones)
\dx                -- extensions (cube, earthdistance, pgaudit, pg_stat_statements)
SELECT pg_size_pretty(pg_database_size('commute')) AS db_size;
SELECT count(*) FROM commute_trafficsample;
```
CNPG status overview: `kubectl cnpg status "$CLUSTER" -n "$NS"` (primary, replicas,
replication lag, last backup).

---

## 2. Dumps & backups

> For extracting table data to **CSV** (external analysis, spreadsheets,
> pandas), see [postgres-csv-export.md](postgres-csv-export.md).

### 2a. Logical dump (portable; for schema remap, migrations, off-box copies)
[`scripts/db-dump.sh`](scripts/db-dump.sh):
```bash
./docs/runbooks/scripts/db-dump.sh                 # custom-format -> backups/commute-<ts>.dump
./docs/runbooks/scripts/db-dump.sh --schema-only
./docs/runbooks/scripts/db-dump.sh --plain         # gzipped SQL
```

### 2b. CNPG-native physical backups (the operational backup)
Two homelab-friendly options, both declarative:

**Longhorn CSI VolumeSnapshots** (no object store needed):
```yaml
# in the Cluster spec
spec:
  backup:
    volumeSnapshot:
      className: longhorn          # Longhorn CSI VolumeSnapshotClass
---
apiVersion: postgresql.cnpg.io/v1
kind: ScheduledBackup
metadata: { name: traffinator-db-daily, namespace: traffinator }
spec:
  schedule: "0 3 * * *"
  backupOwnerReference: self
  cluster: { name: traffinator-db }
  method: volumeSnapshot
```

**Barman object store** (S3/MinIO — enables full PITR; closer to cloud prod):
```yaml
spec:
  backup:
    barmanObjectStore:
      destinationPath: s3://traffinator-backups/
      endpointURL: https://minio.oue.home      # or AWS S3
      s3Credentials:
        accessKeyId:     { name: backup-creds, key: ACCESS_KEY_ID }
        secretAccessKey: { name: backup-creds, key: ACCESS_SECRET_KEY }
    retentionPolicy: "7d"
```
On-demand: `kubectl cnpg backup "$CLUSTER" -n "$NS"`. **Test restores** — an
untested backup is a hope, not a backup (§3/§4).

> CNPG also continuously archives WAL when `barmanObjectStore` is set, enabling
> point-in-time recovery (`bootstrap.recovery` with a `recoveryTarget`).

---

## 3. Restore — full

CNPG restores are **bootstrap-time** (a new Cluster recovers from a backup):
```yaml
spec:
  bootstrap:
    recovery:
      source: traffinator-db
  externalClusters:
    - name: traffinator-db
      barmanObjectStore: { destinationPath: s3://traffinator-backups/, ... }
```
For a quick logical restore into an existing DB (dev/testing):
```bash
kubectl -n "$NS" cp backup.dump "$(pg_pod):/tmp/backup.dump"
kubectl -n "$NS" exec -i "$(pg_pod)" -- env PGPASSWORD="$(pg_password)" \
  pg_restore --no-owner --clean --if-exists -j4 -U "$PG_USER" -d commute /tmp/backup.dump
```

---

## 4. Restore into a DIFFERENT schema

Use case: load a copy into `staging`/per-tenant/`snapshot_*` alongside live
`public` (testing, experiments). [`scripts/db-restore-to-schema.sh`](scripts/db-restore-to-schema.sh):
```bash
./docs/runbooks/scripts/db-restore-to-schema.sh backups/commute-<ts>.dump staging
```
**Mechanism** (portable, no fragile text rewriting): load the dump into a
throwaway DB → `ALTER SCHEMA public RENAME TO staging` → re-dump that schema →
restore into the destination DB. Verify:
```sql
SELECT count(*) FROM staging.commute_trafficsample;
```
**Extension caveat:** `cube`/`earthdistance` aren't freely relocatable; for pure
table/data remaps this is a non-issue, otherwise keep extensions in `public`.
Needs admin/superuser (the script uses the `${CLUSTER}-superuser` secret, so the
cluster must have `enableSuperuserAccess: true`).

---

## 5. Roles, credentials & extensions (CNPG-managed)

- CNPG creates the **app role** (owner of the app DB, *not* a superuser) and
  manages its password in `${CLUSTER}-app`. Point `DATABASE_URL` at the `-rw`
  service with those creds.
- Declare extra roles declaratively with `spec.managed.roles` (login, perms,
  password from a Secret) instead of hand-running `CREATE ROLE`.
- **Rotation:** update the Secret CNPG watches (or let CNPG manage it); the app
  reconnects. No manual `ALTER ROLE` drift.
- **Extensions need superuser**, but the app user isn't one. Pre-create them at
  bootstrap so the app user never needs elevation and Django's
  `CREATE EXTENSION IF NOT EXISTS` becomes a no-op:
  ```yaml
  spec:
    bootstrap:
      initdb:
        database: commute
        owner: commute
        postInitApplicationSQL:          # runs as superuser on the app DB
          - CREATE EXTENSION IF NOT EXISTS cube;
          - CREATE EXTENSION IF NOT EXISTS earthdistance;
          - CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
          - CREATE EXTENSION IF NOT EXISTS pgaudit;
  ```

---

## 6. Logical replication (migrate to Aurora / managed Postgres)

Logical replication is the cross-platform migration tool (physical/streaming
won't work to Aurora's storage). **CNPG runs `wal_level=logical` by default**, so
the source is ready. (Generic mechanism — applies to Aurora, Cloud SQL, Azure DB.
AWS DMS is the managed alternative; native logical replication is the better
learning exercise and free.)

### 6a. Publish on the source
Replicated tables need a replica identity — a primary key suffices (Traffinator's
tables all have `id` PKs).
```sql
CREATE PUBLICATION traffinator_pub FOR ALL TABLES;
```
CNPG can also manage this declaratively via a `Publication` CR (newer versions).

### 6b. Pre-create schema + extensions on the target
Logical replication copies **data, not DDL**. Create structure on the target
first (run the app migrations against it, or restore a `--schema-only` dump from
§2a); ensure `cube`/`earthdistance` exist there too.

### 6c. Subscribe on the target (e.g. Aurora)
```sql
CREATE SUBSCRIPTION traffinator_sub
  CONNECTION 'host=<source-rw-endpoint> port=5432 dbname=commute user=repluser password=...'
  PUBLICATION traffinator_pub;     -- initial COPY, then streams changes
```
Source must be reachable from the target (VPN, public endpoint + SG, or an
`kubectl port-forward`/SSH tunnel for a test). Monitor:
```sql
-- source:  SELECT * FROM pg_stat_replication; SELECT slot_name,active FROM pg_replication_slots;
-- target:  SELECT srsubstate FROM pg_subscription_rel;   -- 'r' = streaming
```

### 6d. Cutover
1. Let initial copy finish; lag → ~0.
2. **Sequences aren't replicated** — bump on target:
   `SELECT setval('commute_trafficsample_id_seq',(SELECT max(id) FROM commute_trafficsample));` (per sequence).
3. Stop writes on source (scale backend to 0); confirm lag 0.
4. Repoint `DATABASE_URL` to the target; redeploy.
5. `DROP SUBSCRIPTION traffinator_sub;` on the target.

---

## 7. Auditing with pgAudit → existing log pipeline

### 7a. Enable pgAudit in the Cluster (no custom image)
CNPG operand images include pgAudit; turn it on via the Cluster spec (combine
with `pg_stat_statements` from §8):
```yaml
spec:
  postgresql:
    shared_preload_libraries:
      - pgaudit
      - pg_stat_statements
    parameters:
      pgaudit.log: "write,ddl,role"     # audited classes; tune to taste
      pgaudit.log_catalog: "off"
      log_destination: "jsonlog"        # structured; easy to ship/query
  # extension created at bootstrap (see §5)
```
CNPG logs to stdout, so the records land in the container log stream.

### 7b. Shipping — already handled by Vector
The homelab **Vector DaemonSet** already tails all pod stdout → **Loki** (full
stream) and **BetterStack Logs** (its `filter_noise` path). So pgAudit records
flow to both with **no new agent**. Notes:
1. Vector's `filter_noise` drops `log_level == "info"`; pgAudit emits at Postgres
   `LOG` level (→ not "info"), so it passes — confirm in Grafana → Explore
   (Loki), and if you want it guaranteed, allow
   `.kubernetes.container_name == "postgres"` in `filter_noise`.
2. For easy queries, add a Vector label keyed on the CNPG pod
   (`cnpg.io/cluster`), then: `{app="traffinator-db"} | json`.

---

## 8. Metrics & query performance

### 8a. CNPG built-in exporter + PodMonitor (no sidecar)
CNPG exposes Prometheus metrics on each instance and can emit a `PodMonitor`:
```yaml
spec:
  monitoring:
    enablePodMonitor: true
    # custom metrics (incl. pg_stat_statements) via a ConfigMap:
    customQueriesConfigMap:
      - name: cnpg-queries
        key: queries.yaml
```
**Gotcha:** kube-prometheus-stack only selects PodMonitors matching its selector
— label the PodMonitor `release: prometheus-stack` (CNPG lets you add labels via
`monitoring.podMonitorMetricRelabelings`/chart values) or set
`podMonitorSelectorNilUsesHelmValues: false` in `apps/prometheus-stack/values.yml`.

CNPG ships a Grafana dashboard — import it into the existing Grafana at
`grafana.oue.home` (`kubectl cnpg install grafana-dashboard`, or grab the JSON
from the CNPG repo).

### 8b. Query performance with pg_stat_statements
```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;   -- (pre-created at bootstrap)
SELECT round(total_exec_time::numeric,1) AS total_ms, calls,
       round(mean_exec_time::numeric,2) AS mean_ms, query
FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;
```
Custom-queries ConfigMap (exposes top-statement metrics to Prometheus):
```yaml
apiVersion: v1
kind: ConfigMap
metadata: { name: cnpg-queries, namespace: traffinator }
data:
  queries.yaml: |
    pg_stat_statements:
      query: "SELECT queryid::text, calls, total_exec_time, mean_exec_time FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20"
      metrics:
        - queryid: {usage: "LABEL", description: "Query ID"}
        - calls: {usage: "COUNTER", description: "Times executed"}
        - total_exec_time: {usage: "COUNTER", description: "Total ms"}
        - mean_exec_time: {usage: "GAUGE", description: "Mean ms"}
```
Also learn `EXPLAIN (ANALYZE, BUFFERS)` on the earthdistance cache lookup — a
good GiST-index case study.

### 8c. BetterStack — deferred
Get it working locally in Grafana first; wiring DB metrics to BetterStack
(Prometheus `remote_write` or via Vector) comes after. (Logs already reach
BetterStack via Vector today.)

---

## 9. Status & follow-ups

**Resolved:** CNPG is the chosen Postgres approach; pgAudit via Cluster config
(no custom image); replication kept generic (learning); BetterStack metrics
deferred; runbook committed to the traffinator repo (Conventional Commits).

**Follow-ups (ArgoCD/operator session — separate):**
- Install the **CNPG operator** as an ArgoCD Application in the homelab repo.
- Replace the Helm chart's Postgres Deployment with a CNPG **`Cluster`** (storage
  `longhorn`; instances ≥2 for HA; bootstrap initdb + `postInitApplicationSQL`
  extensions; `shared_preload_libraries` for pgaudit/pg_stat_statements;
  `monitoring.enablePodMonitor`; a `ScheduledBackup`). Point the backend's
  `DATABASE_URL` at the `${CLUSTER}-rw` service using the `${CLUSTER}-app` secret.
- Decide backup target: Longhorn VolumeSnapshots vs MinIO/S3 Barman (PITR).
- Later: BetterStack metrics; explore performance-tuned operand images.
