#!/usr/bin/env bash
# Restore a custom-format dump into a DIFFERENT schema of the target database.
#
# Technique (robust + portable): load the dump into a throwaway database, rename
# its `public` schema to the target name, re-dump just that schema, then restore
# it into the destination database. Avoids fragile text rewriting of the dump.
#
# Usage:
#   ./db-restore-to-schema.sh <dump.dump> <target_schema> [target_db]
# Example:
#   ./db-restore-to-schema.sh backups/commute-20260613.dump staging
#
# Caveat: PostgreSQL extensions (e.g. cube/earthdistance) are not freely
# relocatable. This script remaps application tables/data cleanly; if your dump
# creates extensions you may need them to stay in `public` (see the runbook).

set -euo pipefail
cd "$(dirname "$0")"
source ./db-env.sh

DUMP="${1:?path to a custom-format dump (.dump) required}"
TARGET_SCHEMA="${2:?target schema name required}"
TARGET_DB="${3:-$PG_DB}"
[[ -f "$DUMP" ]] || { echo "no such file: $DUMP" >&2; exit 1; }

POD="$(pg_pod)"
PGPASSWORD="$(pg_password)"
TMPDB="remap_$(date +%s)"
REMOTE_SRC="/tmp/${TMPDB}-src.dump"
REMOTE_OUT="/tmp/${TMPDB}-remapped.dump"

run() { kubectl -n "$NS" exec -i "$POD" -- env PGPASSWORD="$PGPASSWORD" "$@"; }

cleanup() {
  run psql -U "$PG_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$TMPDB\";" >/dev/null 2>&1 || true
  kubectl -n "$NS" exec "$POD" -- sh -c "rm -f '$REMOTE_SRC' '$REMOTE_OUT'" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "1/5 copying dump into pod..." >&2
kubectl -n "$NS" cp "$DUMP" "$POD:$REMOTE_SRC"

echo "2/5 loading into throwaway db '$TMPDB'..." >&2
run psql -U "$PG_USER" -d postgres -c "CREATE DATABASE \"$TMPDB\";"
run pg_restore --no-owner --no-privileges -U "$PG_USER" -d "$TMPDB" "$REMOTE_SRC" || true

echo "3/5 renaming public -> '$TARGET_SCHEMA'..." >&2
run psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$TMPDB" \
  -c "ALTER SCHEMA public RENAME TO \"$TARGET_SCHEMA\";"

echo "4/5 re-dumping schema '$TARGET_SCHEMA'..." >&2
run pg_dump -U "$PG_USER" -Fc -n "$TARGET_SCHEMA" "$TMPDB" -f "$REMOTE_OUT"

echo "5/5 restoring '$TARGET_SCHEMA' into '$TARGET_DB'..." >&2
run pg_restore --no-owner --no-privileges -U "$PG_USER" -d "$TARGET_DB" "$REMOTE_OUT"

echo "Done. Verify:  SELECT * FROM \"$TARGET_SCHEMA\".commute_trafficsample LIMIT 1;" >&2
