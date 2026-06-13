#!/usr/bin/env bash
# Shared helpers for the Postgres runbook scripts — targets a CloudNativePG
# (CNPG) cluster.  Source this: `source db-env.sh`  (override vars via env)
#
#   NS       — namespace                         (default: traffinator)
#   CLUSTER  — CNPG Cluster name                 (default: traffinator-db)
#   PG_DB    — application database              (default: commute)
#
# CNPG conventions used here:
#   - primary pod selected by labels cnpg.io/cluster + role=primary
#   - admin creds from the <cluster>-superuser Secret (enableSuperuserAccess:
#     true). Falls back to <cluster>-app for non-admin use.
#   - service <cluster>-rw routes to the primary.

set -euo pipefail

NS="${NS:-traffinator}"
CLUSTER="${CLUSTER:-traffinator-db}"
PG_DB="${PG_DB:-commute}"

_secret_key() {  # _secret_key <secret> <key>
  kubectl -n "$NS" get secret "$1" -o jsonpath="{.data.$2}" 2>/dev/null | base64 -d
}

# Admin user/password: prefer the superuser secret, else the app secret.
_admin_secret() {
  if kubectl -n "$NS" get secret "${CLUSTER}-superuser" >/dev/null 2>&1; then
    echo "${CLUSTER}-superuser"
  else
    echo "${CLUSTER}-app"
  fi
}

PG_USER="${PG_USER:-$(_secret_key "$(_admin_secret)" username)}"

pg_password() { _secret_key "$(_admin_secret)" password; }

pg_pod() {
  kubectl -n "$NS" get pod \
    -l "cnpg.io/cluster=${CLUSTER},role=primary" \
    -o jsonpath='{.items[0].metadata.name}'
}

# psql inside the primary pod. Usage: pg_psql [-d otherdb] -c "SQL"
pg_psql() {
  local pod; pod="$(pg_pod)"
  kubectl -n "$NS" exec -i "$pod" -- \
    env PGPASSWORD="$(pg_password)" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" "$@"
}

# Stream a command's stdout out of the primary pod (no TTY, binary-safe).
# Usage: pg_exec pg_dump -Fc "$PG_DB"
pg_exec() {
  local pod; pod="$(pg_pod)"
  kubectl -n "$NS" exec -i "$pod" -- env PGPASSWORD="$(pg_password)" "$@"
}
