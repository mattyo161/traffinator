# Runbook — Export Postgres tables to CSV

Extract table data (or query results) to CSV for external analysis, conversion,
spreadsheets, pandas, BI tools, etc. Companion to
[postgres-operations.md](postgres-operations.md); uses the same CNPG-aware
helpers in [`scripts/`](scripts/).

The database runs in-cluster (CloudNativePG), so the technique throughout is
**server-side `COPY ... TO STDOUT` streamed out of the primary pod** — the CSV
lands on your local machine and nothing is left behind in the pod.

```bash
export NS=traffinator CLUSTER=traffinator-db PG_DB=commute
```

> `\copy` vs `COPY`: psql's `\copy` writes to the *client's* filesystem — but our
> client is inside the pod, so the file would be stuck there. `COPY ... TO
> STDOUT` streams over the connection, which we capture locally. That's why the
> script uses `COPY TO STDOUT`, not `\copy`.

---

## 1. Quick exports with the script

[`scripts/db-export-csv.sh`](scripts/db-export-csv.sh):

```bash
# one table -> exports/commute_trafficsample-<ts>.csv
./docs/runbooks/scripts/db-export-csv.sh commute_trafficsample

# several tables
./docs/runbooks/scripts/db-export-csv.sh commute_trafficsample commute_routegeometry

# every base table in the schema
./docs/runbooks/scripts/db-export-csv.sh --all

# every table, gzipped (good for the big sample table)
./docs/runbooks/scripts/db-export-csv.sh --all --gzip

# a custom query (filtered / joined / shaped for analysis)
./docs/runbooks/scripts/db-export-csv.sh \
  --query "SELECT day_of_week, time_of_day, duration_typical_s
           FROM commute_trafficsample WHERE vector='departure'" \
  -o exports/departures.csv

# export from a non-default schema (e.g. a remapped 'staging' copy)
./docs/runbooks/scripts/db-export-csv.sh --schema staging commute_trafficsample
```
Output goes to `./exports/`. All files include a header row.

---

## 2. One-liners (no script)

Single table:
```bash
source docs/runbooks/scripts/db-env.sh
pg_psql -c "COPY (SELECT * FROM commute_trafficsample) TO STDOUT WITH (FORMAT csv, HEADER true)" \
  > commute_trafficsample.csv
```

Filtered/shaped query:
```bash
pg_psql -c "COPY (
    SELECT day_of_week, time_of_day,
           round(duration_typical_s/60.0, 1) AS typical_min
    FROM commute_trafficsample
    WHERE vector = 'departure'
    ORDER BY day_of_week, time_of_day
  ) TO STDOUT WITH (FORMAT csv, HEADER true)" > departures.csv
```

Via the CNPG plugin instead of the helper:
```bash
kubectl cnpg psql traffinator-db -n traffinator -- -d commute -c \
  "COPY (SELECT * FROM commute_routegeometry) TO STDOUT WITH (FORMAT csv, HEADER true)" \
  > routes.csv
```

---

## 3. Format options

`COPY ... WITH (...)` knobs (Postgres `FORMAT csv`):

| Need | Option |
|---|---|
| Header row | `HEADER true` |
| Tab-separated (TSV) | `DELIMITER E'\t'` |
| Custom NULL marker | `NULL 'NULL'` (default is empty string) |
| Force-quote all fields | `FORCE_QUOTE *` |
| Different quote/escape | `QUOTE '"'`, `ESCAPE '"'` |
| Encoding | `ENCODING 'UTF8'` |

The script exposes `--delimiter` and `--gzip`; for anything more exotic, use the
one-liner form and add options.

### JSONB columns (e.g. `raw_response`)
JSONB exports as a single CSV field containing JSON text, correctly quoted —
fine for pandas (`pd.read_csv` then `json.loads` the column) but awkward in
Excel. To flatten on export, pull the fields you want:
```sql
COPY (
  SELECT id, vector, day_of_week, time_of_day,
         raw_response->>'queried_departure' AS queried_departure
  FROM commute_trafficsample
) TO STDOUT WITH (FORMAT csv, HEADER true)
```
To omit a big JSONB column entirely, select explicit columns rather than `*`.

---

## 4. Large tables

- **Stream + gzip** to keep memory/disk low: the script's `--gzip`, or
  `... TO STDOUT ... | gzip > file.csv.gz`.
- **Chunk** by a key if you need smaller files:
  `WHERE id BETWEEN 1 AND 100000`, etc.
- For very large extracts prefer running off a **read replica** (`${CLUSTER}-ro`
  service) so you don't load the primary — point `db-env.sh` at it or use
  `kubectl port-forward svc/traffinator-db-ro`.

---

## 5. Using the CSV downstream

- **pandas:** `df = pd.read_csv("exports/commute_trafficsample-<ts>.csv")`
  (gzip is read transparently if the name ends in `.gz`).
- **Excel/Sheets:** import directly; for non-ASCII set the import encoding to
  UTF-8.
- **Round-trip back into Postgres** (e.g. into another DB/schema):
  ```bash
  pg_psql -c "\copy target_table FROM STDIN WITH (FORMAT csv, HEADER true)" < file.csv
  # (here \copy is correct — reading from your local stdin into the server)
  ```

---

## 6. Notes & cautions

- **PII / secrets:** exported CSVs are plaintext on your laptop — treat the
  `exports/` dir accordingly and don't commit it (add to `.gitignore` if you
  keep exports in a repo).
- Exports are **point-in-time snapshots**; they don't reflect later writes.
- `COPY TO STDOUT` needs only read access — the app/read-only role is enough; no
  superuser required (unlike the schema-remap restore).
