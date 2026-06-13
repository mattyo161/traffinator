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

## 1. Build images and get them onto the cluster

The chart does not build images. Build from the repo root and either push to a
registry your nodes can reach, or import straight into k3s containerd:

```bash
# Build
docker build -t traffinator-backend:1.0.0 ./backend
docker build -t traffinator-frontend:1.0.0 ./frontend

# Option A — import into k3s (single node, no registry needed)
docker save traffinator-backend:1.0.0  | sudo k3s ctr images import -
docker save traffinator-frontend:1.0.0 | sudo k3s ctr images import -

# Option B — push to your registry, then set image.*.repository in values
#   docker tag traffinator-backend:1.0.0 registry.example/traffinator-backend:1.0.0
#   docker push registry.example/traffinator-backend:1.0.0
```

With Option A keep `image.pullPolicy: IfNotPresent` (the default) so k3s uses
the imported image instead of trying to pull it.

## 2. Install

```bash
helm install traffinator deploy/helm/traffinator \
  --namespace traffinator --create-namespace \
  --set ingress.host=traffinator.lan
```

Provide secrets inline or, better, with a values file (`-f my-values.yaml`):

```yaml
secrets:
  googleMapsApiKey: "AIza..."        # or leave blank and use the setup screen
  googleOauthClientId: "...apps.googleusercontent.com"  # optional, enables sign-in
  openRouteServiceApiKey: ""         # optional; blank -> public OSRM for routing
```

Then point the hostname at your node (e.g. add `traffinator.lan` to your
router's DNS, or `/etc/hosts` for a quick test).

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
| `backend.image.repository` / `.tag` | `traffinator-backend` / `1.0.0` | |
| `frontend.image.repository` / `.tag` | `traffinator-frontend` / `1.0.0` | |
| `image.pullPolicy` | `IfNotPresent` | Right for k3s-imported images |
| `ingress.enabled` / `.host` / `.className` | `true` / `traffinator.local` / `traefik` | |
| `ingress.tls.enabled` / `.secretName` | `false` / `traffinator-tls` | Bring your own cert secret |
| `postgres.enabled` | `true` | Set `false` + `externalDatabase.url` for Supabase/external |
| `postgres.persistence.size` | `5Gi` | |
| `postgres.persistence.storageClass` | `""` | `""` = cluster default (`local-path`) |
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
