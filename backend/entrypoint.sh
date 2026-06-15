#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import os, time, sys
import psycopg
import dj_database_url

cfg = dj_database_url.parse(os.environ["DATABASE_URL"])
dsn = (
    f"host={cfg['HOST']} port={cfg.get('PORT') or 5432} "
    f"dbname={cfg['NAME']} user={cfg['USER']} password={cfg['PASSWORD']}"
)
for attempt in range(60):
    try:
        psycopg.connect(dsn, connect_timeout=3).close()
        print("Database is up.")
        sys.exit(0)
    except Exception as exc:
        print(f"  not ready yet ({exc.__class__.__name__}), retrying...")
        time.sleep(2)
print("Database never became available.", file=sys.stderr)
sys.exit(1)
PY

# Any arguments override the default server startup (e.g.
# `docker compose run --rm backend python manage.py test commute`).
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

echo "Applying migrations..."
python manage.py migrate --noinput

# Prometheus multiprocess dir: gunicorn runs >1 worker, so prometheus_client
# must aggregate metrics across them via a shared directory. Set+exported only on
# this server path (NOT via compose/k8s env) so it never leaks into one-off
# `docker compose run ... manage.py test` invocations, which exec above before
# reaching here and would otherwise try (and fail) to use multiprocess mode.
# Wipe the dir on boot so stale samples from a previous container don't leak in.
export PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus-multiproc}"
echo "Preparing Prometheus multiprocess dir: $PROMETHEUS_MULTIPROC_DIR"
rm -rf "$PROMETHEUS_MULTIPROC_DIR"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR"

echo "Starting gunicorn..."
# Long timeout: an analysis run can hold the request open while many
# Google Maps calls are in flight.
exec gunicorn config.wsgi:application \
    --config /app/gunicorn.conf.py \
    --bind 0.0.0.0:8000 \
    --workers 2 \
    --threads 8 \
    --timeout 900 \
    --access-logfile - \
    --error-logfile -
