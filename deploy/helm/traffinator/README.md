# Traffinator Helm chart

Deploys Traffinator (Django API + React SPA + PostgreSQL) to a Kubernetes
cluster. Defaults target a **k3s homelab** single node: Traefik ingress and the
`local-path` storage provisioner.

## Topology

```
Ingress (Traefik) ──> frontend Service (nginx :80) ──/api──> backend Service (gunicorn :8000) ──> postgres Service (:5432, PVC)
```

The frontend is the only externally exposed component; its nginx proxies `/api`
to the backend in-cluster (the chart rewrites the proxy target to the
release's backend Service via a mounted config).

## 1. Images (GHCR via GitHub Actions)

Images are built and pushed to **GitHub Container Registry** by
[`.github/workflows/build-images.yml`](../../../.github/workflows/build-images.yml).
It runs on pushes to `main`, on `v*` tags, and on manual dispatch, producing:

- `ghcr.io/mattyo161/traffinator-backend`
- `ghcr.io/mattyo161/traffinator-frontend`

Each push is tagged with the short git SHA, the branch name, `latest` (on
`main`), and a semver (when you push a `v1.2.3` git tag). On a **multi-node**
cluster, pin the chart to an immutable tag — a SHA or a version — not `latest`,
so every node runs the same image:

```yaml
backend:  { image: { tag: "sha-1a2b3c4" } }   # or "1.0.0" from a v1.0.0 tag
frontend: { image: { tag: "sha-1a2b3c4" } }
```

Leaving `tag: ""` falls back to the chart's `appVersion`.

### Pull secret (only if the GHCR packages are private)

New GHCR packages are private by default. Either make them public
(repo → Packages → package → Settings → Change visibility), or create a pull
secret in the release namespace and reference it:

```bash
kubectl -n traffinator create secret docker-registry ghcr \
  --docker-server=ghcr.io \
  --docker-username=mattyo161 \
  --docker-password=<a PAT or token with read:packages>
```

```yaml
imagePullSecrets:
  - name: ghcr
```

### Local build fallback (no registry)

For a quick single-node test without the registry you can still build and
import into k3s containerd, then point the chart at the local tag with
`pullPolicy: IfNotPresent`:

```bash
docker build -t traffinator-backend:dev ./backend
docker save traffinator-backend:dev | sudo k3s ctr images import -   # repeat per node
# helm ... --set backend.image.repository=traffinator-backend --set backend.image.tag=dev
```

## 2. Install

> **Image prerequisite:** the GHCR images are built by the
> `build-images` workflow, which runs **on push to `main`**. So merge the chart
> (and the app code you want to ship) to `main` first — CI publishes
> `ghcr.io/mattyo161/traffinator-{backend,frontend}` — then deploy. For a quick
> pre-merge test, use the local build+import fallback in §1.

> **Database prerequisite:** the chart defaults to `postgres.mode=cnpg`, which
> creates a CloudNativePG `Cluster` and therefore needs the **CNPG operator**
> installed in the cluster first:
> ```bash
> helm repo add cnpg https://cloudnative-pg.github.io/charts
> helm upgrade --install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace
> ```
> No operator? Use `postgres.mode=bundled` (a simple in-chart Postgres
> Deployment + PVC) or `postgres.mode=external` — see *Database modes* below.

### Homelab (mattyo161/homelab)
A ready overlay is provided — Longhorn storage + Traefik/cert-manager under
`*.oue.home`:

```bash
helm upgrade --install traffinator deploy/helm/traffinator \
  -n traffinator --create-namespace \
  -f deploy/helm/traffinator/values-homelab.yaml \
  -f my-secrets.yaml          # see below; keep secrets out of git
```
Opens at `https://traffinator.oue.home` (add the host to DNS / `/etc/hosts`).
After CI publishes images, pin the tag in the overlay
(`backend.image.tag` / `frontend.image.tag`) to a SHA or version.

### Generic
```bash
helm install traffinator deploy/helm/traffinator \
  --namespace traffinator --create-namespace \
  --set ingress.host=traffinator.lan
```

Provide secrets with a values file (`-f my-secrets.yaml`), not inline:

```yaml
secrets:
  googleMapsApiKey: "AIza..."        # or leave blank and use the setup screen
  googleOauthClientId: "...apps.googleusercontent.com"  # optional, enables sign-in
  openRouteServiceApiKey: ""         # optional; blank -> public OSRM for routing
```

Then point the hostname at your node (e.g. add the host to your router's DNS, or
`/etc/hosts` for a quick test).

### Database modes (`postgres.mode`)

The chart provisions Postgres one of three ways:

**`cnpg` (default)** — a CloudNativePG `Cluster` (HA, backups, metrics; operand
images bundle pgaudit/pg_stat_statements/contrib). Requires the operator
(prerequisite above). The chart pre-creates the `cube`/`earthdistance`/
`pg_stat_statements` extensions at bootstrap (so the app role needs no
elevation), and the backend reads `DATABASE_URL` from the CNPG `<release>-postgres-app`
Secret's `uri` key — no DB password ever lands in chart values. Tunables:
```yaml
postgres:
  mode: cnpg
  cnpg:
    instances: 2                  # HA
    storage: { size: 5Gi, storageClass: longhorn }
    monitoring: { enablePodMonitor: true }   # with kube-prometheus-stack
    superuserAccess: false        # true for admin ops (e.g. schema-remap restores)
    # WAL archiving for PITR via the Barman Cloud Plugin. Only wires the plugin
    # onto the Cluster — create the ObjectStore + ScheduledBackup yourself.
    backup: { enabled: true, objectStoreName: traffinator-store }
```
See [../../docs/runbooks/postgres-operations.md](../../docs/runbooks/postgres-operations.md)
for day-2 operations (backups, restores, replication, metrics).

**`bundled`** — a simple in-chart Postgres `Deployment` + PVC. No operator
needed; good for a quick start or clusters without CNPG:
```yaml
postgres:
  mode: bundled
  bundled:
    persistence: { enabled: true, storageClass: longhorn, size: 5Gi }
```

**`external`** — bring your own database (Supabase / RDS / Aurora / an existing
CNPG cluster). Provide a URL, or (preferred) point at an existing Secret:
```yaml
postgres:
  mode: external
externalDatabase:
  existingSecret: my-db-app       # e.g. a CNPG <cluster>-app secret
  existingSecretKey: uri
  # or: url: "postgresql://user:pass@host:5432/db"
```
The target must have `cube` and `earthdistance` available.

## 3. Upgrade / uninstall

```bash
helm upgrade traffinator deploy/helm/traffinator -n traffinator -f my-values.yaml
helm uninstall traffinator -n traffinator
```

The PVC is intentionally **not** deleted on uninstall (so your cache and stored
key survive). Remove it manually if you want a clean slate:

```bash
kubectl -n traffinator delete pvc -l app.kubernetes.io/instance=traffinator
```

## Publishing the chart to GHCR (OCI)

CI publishes the packaged chart to GitHub Container Registry as an OCI artifact
so it can be consumed without cloning the repo (e.g. by ArgoCD). Published to
**`ghcr.io/mattyo161/charts/traffinator:<version>`** via `GITHUB_TOKEN` +
`packages: write` (no PAT). [`publish-chart.yml`](../../../.github/workflows/publish-chart.yml)
publishes in two ways:

- **On every app release (primary):** `release.yml` calls it with the
  semantic-release version, packaging with `--version`/`--app-version` = the app
  version. So **chart and app track together** — releasing app `0.4.0` also
  publishes chart `0.4.0`. This is the main path; you don't bump `Chart.yaml`
  by hand for normal releases.
- **On a chart-only change to `main` (or manual dispatch):** publishes the
  `version:` from `Chart.yaml`. For an out-of-band chart change without an app
  release, bump that field (OCI tags are immutable; the job skips with a warning
  if the version already exists).

`Chart.yaml`'s `version:` is therefore a **baseline** for manual/chart-only
publishes; released versions come from the app version.

> **Visibility:** the `traffinator` chart package is public (matches the public
> container images), so no pull secret is needed.

Pull/inspect manually:
```bash
helm show chart oci://ghcr.io/mattyo161/charts/traffinator --version 0.3.0
helm pull oci://ghcr.io/mattyo161/charts/traffinator --version 0.3.0
helm upgrade --install traffinator oci://ghcr.io/mattyo161/charts/traffinator \
  --version 0.3.0 -n traffinator --create-namespace -f my-values.yaml
```

### Deploy via ArgoCD from the OCI chart
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: traffinator
  namespace: argocd
spec:
  project: default
  sources:
    - repoURL: ghcr.io/mattyo161/charts      # note: no oci:// prefix here
      chart: traffinator
      targetRevision: 0.3.0                   # pin the chart version
      helm:
        valueFiles:
          - $values/deploy/helm/traffinator/values-homelab.yaml
    - repoURL: https://github.com/mattyo161/traffinator.git
      targetRevision: HEAD
      ref: values
  destination:
    server: https://kubernetes.default.svc
    namespace: traffinator
  syncPolicy:
    syncOptions: [CreateNamespace=true]
```
(If the chart package is private, register the OCI repo in ArgoCD with
credentials + `enableOCI: true`.)

## Key values

| Key | Default | Notes |
|---|---|---|
| `backend.image.repository` / `.tag` | `ghcr.io/mattyo161/traffinator-backend` / `""` | `""` → chart appVersion; pin a SHA/version for multi-node |
| `frontend.image.repository` / `.tag` | `ghcr.io/mattyo161/traffinator-frontend` / `""` | as above |
| `image.pullPolicy` | `IfNotPresent` | Fine with immutable tags |
| `imagePullSecrets` | `[]` | `[{name: ghcr}]` if GHCR packages are private |
| `ingress.enabled` / `.host` / `.className` | `true` / `traffinator.local` / `traefik` | |
| `ingress.tls.enabled` / `.secretName` | `false` / `traffinator-tls` | Bring your own cert secret |
| `postgres.mode` | `cnpg` | `cnpg` \| `bundled` \| `external` (see *Database modes*) |
| `postgres.cnpg.instances` | `2` | HA replica count (cnpg mode) |
| `postgres.cnpg.storage.{size,storageClass}` | `5Gi` / `""` | cnpg mode; set `longhorn` on the homelab |
| `postgres.cnpg.monitoring.enablePodMonitor` | `false` | DB metrics via kube-prometheus-stack |
| `postgres.cnpg.superuserAccess` | `false` | Create the `<cluster>-superuser` secret for admin ops |
| `postgres.cnpg.backup.enabled` / `.objectStoreName` | `false` / `""` | Wire the Barman Cloud WAL-archiver plugin onto the Cluster (PITR). Requires an existing `barmancloud.cnpg.io/ObjectStore`; ScheduledBackup managed outside the chart |
| `postgres.cnpg.pgaudit.enabled` | `false` | Enable pgAudit (adds `pgaudit` to `shared_preload_libraries`, creates the extension, sets audit params) |
| `postgres.cnpg.pgaudit.log` / `.logCatalog` | `write,ddl,role` / `false` | `pgaudit.log` classes and `pgaudit.log_catalog` |
| `postgres.bundled.persistence.{size,storageClass}` | `5Gi` / `""` | bundled mode |
| `externalDatabase.url` | `""` | external mode: plain connection URL |
| `externalDatabase.existingSecret` / `.existingSecretKey` | `""` / `uri` | external mode: pull `DATABASE_URL` from an existing secret (e.g. a CNPG `<cluster>-app` secret) |
| `secrets.googleMapsApiKey` | `""` | Blank → configure via in-app setup screen |
| `secrets.googleOauthClientId` | `""` | Enables Google sign-in; also served to the SPA |
| `secrets.openRouteServiceApiKey` | `""` | Blank → routing falls back to public OSRM |
| `secrets.djangoSecretKey` / `postgres.bundled.password` | `""` | Blank → generated and **preserved across upgrades** |
| `secrets.existingSecret` | `""` | Manage all credentials in your own Secret instead |

## Notes

- **Generated credentials persist across upgrades.** In `bundled` mode, with
  `djangoSecretKey` and `postgres.bundled.password` left blank, the chart
  generates them on first install and re-reads them from the live Secret on
  upgrades (so the DB password never drifts away from the data on the PVC). This
  relies on `helm`'s `lookup`, which is empty under `helm template`/`--dry-run`
  — those render fresh randoms, for inspection only. In `cnpg` mode the operator
  owns the DB credentials (`<release>-postgres-app` Secret).
- **Migrations** run from the backend entrypoint on pod start. Keep
  `backend.replicas: 1` unless you move `migrate` into a dedicated Job.
- **Extensions:** `cnpg` mode pre-creates `cube`/`earthdistance` at bootstrap.
  In `bundled`/`external` mode the app's migration runs `CREATE EXTENSION` (the
  bundled superuser handles it; an external DB must allow these extensions).

## External Postgres example

```yaml
postgres:
  mode: external
externalDatabase:
  url: "postgresql://postgres:PASS@db.PROJECT.supabase.co:5432/postgres"
```
