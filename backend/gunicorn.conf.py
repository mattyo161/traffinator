"""Gunicorn config — wires up prometheus_client multiprocess mode.

With multiple gunicorn workers each process keeps its own metric values; the
/metrics view can only aggregate them if every worker writes to a shared
PROMETHEUS_MULTIPROC_DIR (set in entrypoint.sh). When a worker dies its files
must be reaped via mark_process_dead so its Counter/Histogram samples are
flushed into the aggregate and live Gauges don't linger. See
https://prometheus.github.io/client_python/multiprocess/.
"""

import os


def child_exit(server, worker):
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
