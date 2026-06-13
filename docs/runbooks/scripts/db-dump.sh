#!/usr/bin/env bash
# Dump the Traffinator database from the in-cluster Postgres pod to a local file.
#
# Usage:
#   ./db-dump.sh                       # custom-format dump -> ./backups/<db>-<ts>.dump
#   ./db-dump.sh --plain               # plain SQL .sql.gz instead of custom format
#   ./db-dump.sh --schema-only         # structure, no data
#   ./db-dump.sh --data-only
#   ./db-dump.sh -o /path/file.dump    # explicit output path
#
# Custom format (default, -Fc) is restorable with pg_restore and supports
# selective/parallel restore. Plain format is a human-readable .sql.

set -euo pipefail
cd "$(dirname "$0")"
source ./db-env.sh

FORMAT="custom"
EXTRA=()
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plain) FORMAT="plain"; shift ;;
    --schema-only) EXTRA+=("--schema-only"); shift ;;
    --data-only) EXTRA+=("--data-only"); shift ;;
    -o) OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

TS="$(date +%Y%m%d-%H%M%S)"
mkdir -p backups

if [[ "$FORMAT" == "custom" ]]; then
  OUT="${OUT:-backups/${PG_DB}-${TS}.dump}"
  echo "Dumping (custom format) -> $OUT" >&2
  pg_exec pg_dump -U "$PG_USER" -Fc "${EXTRA[@]}" "$PG_DB" > "$OUT"
else
  OUT="${OUT:-backups/${PG_DB}-${TS}.sql.gz}"
  echo "Dumping (plain SQL, gzipped) -> $OUT" >&2
  pg_exec pg_dump -U "$PG_USER" "${EXTRA[@]}" "$PG_DB" | gzip > "$OUT"
fi

echo "Done: $OUT ($(du -h "$OUT" | cut -f1))" >&2
