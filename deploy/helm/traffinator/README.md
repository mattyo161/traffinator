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

### Using a CloudNativePG database instead of the bundled Postgres
Once the CNPG operator + a `Cluster` (e.g. `traffinator-db`) exist (see
[../../docs/runbooks/postgres-operations.md](../../docs/runbooks/postgres-operations.md)),
switch the app to it — no password in chart values, pulled from the CNPG app
secret's `uri` key:

```yaml
postgres:
  enabled: false
externalDatabase:
  existingSecret: traffinator-db-app
  existingSecretKey: uri
```

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

## Key values

| Key | Default | Notes |
|---|---|---|
| `backend.image.repository` / `.tag` | `ghcr.io/mattyo161/traffinator-backend` / `""` | `""` → chart appVersion; pin a SHA/version for multi-node |
| `frontend.image.repository` / `.tag` | `ghcr.io/mattyo161/traffinator-frontend` / `""` | as above |
| `image.pullPolicy` | `IfNotPresent` | Fine with immutable tags |
| `imagePullSecrets` | `[]` | `[{name: ghcr}]` if GHCR packages are private |
| `ingress.enabled` / `.host` / `.className` | `true` / `traffinator.local` / `traefik` | |
| `ingress.tls.enabled` / `.secretName` | `false` / `traffinator-tls` | Bring your own cert secret |
| `postgres.enabled` | `true` | Set `false` for external/CNPG (see below) |
| `postgres.persistence.size` | `5Gi` | |
| `postgres.persistence.storageClass` | `""` | `""` = cluster default; set `longhorn` on the homelab |
| `externalDatabase.url` | `""` | Plain connection URL when `postgres.enabled=false` |
| `externalDatabase.existingSecret` / `.existingSecretKey` | `""` / `uri` | Pull `DATABASE_URL` from an existing secret (e.g. a CNPG `<cluster>-app` secret) — keeps the password out of chart values |
| `secrets.googleMapsApiKey` | `""` | Blank → configure via in-app setup screen |
| `secrets.googleOauthClientId` | `""` | Enables Google sign-in; also served to the SPA |
| `secrets.openRouteServiceApiKey` | `""` | Blank → routing falls back to public OSRM |
| `secrets.djangoSecretKey` / `postgres.password` | `""` | Blank → generated and **preserved across upgrades** |
| `secrets.existingSecret` | `""` | Manage all credentials in your own Secret instead |

## Notes

- **Generated credentials persist across upgrades.** With `djangoSecretKey` and
  `postgres.password` left blank, the chart generates them on first install and
  re-reads them from the live Secret on subsequent upgrades (so the DB password
  never drifts away from the data on the PVC). This relies on `helm`'s `lookup`,
  which is empty under `helm template`/`--dry-run` — those render fresh randoms
  and are for inspection only, not installs.
- **Migrations** run from the backend entrypoint on pod start. Keep
  `backend.replicas: 1` unless you move `migrate` into a dedicated Job.
- **External Postgres** must have the `cube` and `earthdistance` extensions
  available (the app's migration runs `CREATE EXTENSION`).

## External Postgres example

```yaml
postgres:
  enabled: false
externalDatabase:
  url: "postgresql://postgres:PASS@db.PROJECT.supabase.co:5432/postgres"
```
