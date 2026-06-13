#!/usr/bin/env bash
# Export Postgres tables or a custom query to CSV on your local machine.
#
# Uses server-side COPY ... TO STDOUT streamed out of the CNPG primary pod, so
# the CSV lands locally (no file left in the pod). Header row included.
#
# Usage:
#   ./db-export-csv.sh commute_trafficsample              # one table -> exports/<table>-<ts>.csv
#   ./db-export-csv.sh commute_trafficsample commute_routegeometry
#   ./db-export-csv.sh --all                              # every base table in 'public'
#   ./db-export-csv.sh --query "SELECT day_of_week, time_of_day, duration_typical_s
#                                FROM commute_trafficsample WHERE vector='departure'" \
#                      -o exports/departures.csv
#   ./db-export-csv.sh --all --gzip                       # gzip each file
#   ./db-export-csv.sh --schema staging commute_trafficsample
#
# Options:
#   --all              export all base tables in the schema
#   --query "SQL"      export the result of an arbitrary SELECT (needs -o)
#   -o <path>          output file (only with --query)
#   --schema <name>    schema to read tables from (default: public)
#   --gzip             gzip the output file(s)
#   --delimiter <c>    field delimiter (default: ,)

set -euo pipefail
cd "$(dirname "$0")"
source ./db-env.sh

SCHEMA="public"
GZIP=0
DELIM=","
QUERY=""
OUT=""
TABLES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) ALL=1; shift ;;
    --query) QUERY="$2"; shift 2 ;;
    -o) OUT="$2"; shift 2 ;;
    --schema) SCHEMA="$2"; shift 2 ;;
    --gzip) GZIP=1; shift ;;
    --delimiter) DELIM="$2"; shift 2 ;;
    -*) echo "unknown option: $1" >&2; exit 2 ;;
    *) TABLES+=("$1"); shift ;;
  esac
done

TS="$(date +%Y%m%d-%H%M%S)"
mkdir -p exports

# COPY options shared by all exports.
copy_opts="FORMAT csv, HEADER true, DELIMITER '${DELIM}'"

write_out() {  # write_out <dest-without-gz>  (reads CSV from stdin)
  local dest="$1"
  if [[ "$GZIP" == "1" ]]; then
    gzip > "${dest}.gz"
    echo "  -> ${dest}.gz ($(du -h "${dest}.gz" | cut -f1))" >&2
  else
    cat > "$dest"
    echo "  -> ${dest} ($(du -h "$dest" | cut -f1))" >&2
  fi
}

export_table() {  # export_table <table>
  local tbl="$1"
  local dest="exports/${tbl}-${TS}.csv"
  echo "Exporting table ${SCHEMA}.${tbl}" >&2
  pg_psql -c "COPY (SELECT * FROM \"${SCHEMA}\".\"${tbl}\") TO STDOUT WITH (${copy_opts})" \
    | write_out "$dest"
}

if [[ -n "$QUERY" ]]; then
  [[ -n "$OUT" ]] || { echo "--query requires -o <path>" >&2; exit 2; }
  mkdir -p "$(dirname "$OUT")"
  echo "Exporting custom query" >&2
  pg_psql -c "COPY (${QUERY}) TO STDOUT WITH (${copy_opts})" | write_out "$OUT"
  exit 0
fi

if [[ "${ALL:-0}" == "1" ]]; then
  echo "Discovering base tables in schema '${SCHEMA}'..." >&2
  mapfile -t TABLES < <(pg_psql -At -c \
    "SELECT tablename FROM pg_tables WHERE schemaname='${SCHEMA}' ORDER BY tablename")
fi

[[ ${#TABLES[@]} -gt 0 ]] || { echo "no tables specified (give names, --all, or --query)" >&2; exit 2; }

for t in "${TABLES[@]}"; do
  export_table "$t"
done
echo "Done. Files in ./exports/" >&2
