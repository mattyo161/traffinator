# Traffinator

> *"I'll be fast."*

A containerized, decoupled web app that analyzes commute times with predictive
traffic modeling — so you can find your nonstop commute and say hasta la vista
to gridlock. A React + Tailwind single-page app talks to a Django REST
API, which serves results from a PostgreSQL spatial/temporal cache and falls
back to the Google Maps Distance Matrix API on cache misses.

```
Browser ──> nginx (frontend, :8900) ──> /api/* ──> Django (backend, :8000) ──> PostgreSQL (cube + earthdistance)
                                                            └──> Google Maps Distance Matrix / Geocoding APIs
```

## Quick start

Prerequisites: Docker with the Compose plugin (`docker compose version` works).

```bash
docker compose up --build
```

Then open **http://localhost:8900**.

On first launch the app shows a setup screen asking for your Google Maps API
key (see below). The key is validated against Google and stored in the
database — you only do this once. If you prefer config files, copy
`.env.example` to `.env` and set `GOOGLE_MAPS_API_KEY` before starting; the
setup screen is then skipped entirely. Environment variables always override
the database-stored key.

## Getting a Google Maps API key

1. Go to the [Google Cloud Console](https://console.cloud.google.com/google/maps-apis/credentials)
   and create (or select) a project. **Billing must be enabled** — predictive
   traffic data is a paid feature (each provides a free monthly usage credit).
2. Enable two APIs on the project:
   - **Distance Matrix API** (traffic predictions)
   - **Geocoding API** (turning addresses into coordinates)
3. Create an API key under *Credentials*.
4. Paste it into the first-launch setup screen, or put it in `.env`.

### About API usage and cost

Each analysis data point on a cache miss costs **3 Distance Matrix calls**
(Google's `optimistic`, `best_guess`, and `pessimistic` traffic models, which
become the chart's min / typical / max). "Arrive by" mode adds **1 extra call**
per point to estimate the departure time. The UI shows the worst-case call
count before you run, and the cache means repeat/nearby analyses are free.

Example: 7 AM–9 AM at 15-minute steps for 5 days = 9 × 5 = 45 points = up to
135 calls on a cold cache, 0 on a warm one.

## Configuration reference

All settings are optional and live in `.env` (see [.env.example](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | *(unset)* | Skips the in-app setup screen; overrides the DB-stored key |
| `APP_PORT` | `8900` | Host port for the web UI |
| `DATABASE_URL` | bundled Postgres | Point at Supabase or any external Postgres |
| `POSTGRES_DB/USER/PASSWORD` | `commute` | Credentials for the bundled Postgres container |
| `ANALYSIS_MAX_WORKERS` | `8` | Parallel Google Maps requests per analysis run |
| `DJANGO_SECRET_KEY` | dev default | Set for production-like deployments |
| `DJANGO_DEBUG` | `0` | Django debug mode |
| `TIER_ENFORCEMENT` | `0` | `1` enforces per-tier analyze limits (see [User tiers](#user-tiers)) |

### Using Supabase instead of the bundled Postgres

1. In the Supabase dashboard: **Database → Extensions** → enable `cube` and
   `earthdistance`.
2. Set `DATABASE_URL` in `.env` to your Supabase connection string
   (Settings → Database → Connection string, URI format).
3. `docker compose up --build` — migrations run automatically against Supabase.
   The bundled `db` container is simply ignored.

## How the cache works

Before any Google call, the backend looks for an existing record where **all**
of the following hold (`commute/services/cache.py`):

1. Origin **and** destination are within a **1-mile radius** of the request's
   coordinates, computed with PostgreSQL's `earthdistance` module
   (`earth_box` GiST-index prefilter + exact `earth_distance` check).
2. The **day of week matches exactly**.
3. The time of day is within an **absolute 4-minute delta** (midnight-safe).
4. The record is **less than 7 days old**.

On a hit the record is served instantly; on a miss the backend fetches live
predictions and writes the result — including the **full raw API responses** —
to the `commute_trafficsample` table.

The **1-mile** match radius above is the default; with tier enforcement on it
becomes per-tier (see below).

## User tiers

Analysis controls are gated by a user **tier** — `ANON` (unauthenticated),
`FREE` (signed in), or `PRO` (granted manually) — covering which interval steps,
days, hour windows, and trip distances are allowed, plus the per-tier cache
match radius. The tier→limits matrix is defined once in **`commute/tiers.py`**;
the backend both enforces it and serves it (with the requester's current tier)
via `GET /api/config`, so the SPA renders the same gray-outs/upsells.

PRO is assigned manually (no billing yet):

```bash
docker compose exec backend python manage.py set_tier you@example.com PRO
```

Enforcement is **off by default** (`TIER_ENFORCEMENT=0`) so the API can ship
ahead of the tier-aware UI; set `TIER_ENFORCEMENT=1` to enforce. When off, the
matrix is still served (the UI can read it) but no request is rejected and the
cache uses its default radius.

## API

`POST /api/analyze`

```json
{
  "origin": {"lat": 40.7128, "lng": -74.0060},
  "destination": {"lat": 40.7484, "lng": -73.9857},
  "vector": "departure",
  "start_hour": 7,
  "end_hour": 9,
  "interval_minutes": 15,
  "days": [0, 1, 2, 3, 4],
  "timezone": "America/New_York"
}
```

- `vector`: `"departure"` (leave at the given times) or `"arrival"` (arrive by
  the given times).
- `days`: 0 = Monday … 6 = Sunday.
- `timezone`: IANA name; the UI sends the browser's automatically.

Response: per-day arrays of `{time, min_s, typical_s, max_s, cached}` plus
`meta` with cache-hit and API-call counts.

Other endpoints:
- `GET /api/config` — runtime config for the SPA (maps configured? Google OAuth
  client id, Apple enabled?).
- `GET /api/setup/status`, `POST /api/setup` (`{"api_key": …}`).
- `POST /api/geocode` (`{"query": "address", "region": "us"}` → up to 5
  candidates in `{"results": [{lat, lng, address}]}`; `region` is an optional
  ccTLD bias the UI derives from the browser locale).
- `POST /api/route` (`{"origin": {lat,lng}, "destination": {lat,lng}}` →
  `{"geometry": [[lat,lng], …], "distance_m", "provider", "cached"}`).
- `POST /api/auth/google` (`{"credential": "<google id token>"}` → `{token, user}`),
  `GET /api/auth/me`, `POST /api/auth/logout`.
- `GET/POST/DELETE /api/saved-routes/` and `/api/saved-addresses/` — require
  `Authorization: Token …`; scoped to the signed-in user.

## Metrics (Prometheus)

The backend exposes Prometheus metrics at **`GET /metrics`** (via
`django-prometheus`). It is served off the backend Service on port 8000 — the
frontend nginx only proxies `/api`, so `/metrics` is in-cluster only, not public.

Besides the stock `django_http_*` request/latency series, Traffinator records
**outbound external-API usage** (`commute/metrics.py`) so you can see paid
(Google Maps) vs free (OSRM/ORS) consumption and prove the cache is avoiding
paid calls:

- `traffinator_external_api_calls_total{provider,endpoint,billable,outcome}` —
  every outbound call, labelled `billable="paid"|"free"` and
  `outcome="ok"|"error"|"cache_hit"`. A `cache_hit` increments by the number of
  live calls the hit *avoided* (3 per traffic point, 4 for arrival-mode), so
  `sum by (billable) (… outcome="cache_hit")` is a direct "calls/cost avoided"
  figure.
- `traffinator_external_api_duration_seconds{provider,endpoint}` — per-provider
  call latency histogram.

**Multi-worker note:** gunicorn runs multiple workers, so `prometheus_client`
runs in multiprocess mode — each worker writes to a shared
`PROMETHEUS_MULTIPROC_DIR` that the `/metrics` view aggregates. `entrypoint.sh`
sets and wipes that dir on boot and `gunicorn.conf.py`'s `child_exit` hook reaps
dead workers (`multiprocess.mark_process_dead`). It's set only on the server
path, so it never leaks into one-off `manage.py test` runs.

In the Helm chart, a `ServiceMonitor` (for kube-prometheus-stack) can be enabled
with `backend.metrics.serviceMonitor.enabled=true`.

## Using the app

- **From / To** — type an address and pick the right match from the typeahead
  dropdown (results are biased toward your browser's region but must be
  explicitly confirmed), or paste raw `lat,lng` coordinates directly.
- **Reverse commute** — the ⇅ button between From and To swaps them, for
  analyzing the return trip.
- **Route preview** — once both points are confirmed, a map (OpenStreetMap
  tiles) draws the actual **road route** and shows the driving distance, with a
  warning if the points are too far apart to plausibly be a commute. Route
  geometry is fetched from a free routing provider and cached in Postgres.
- **Accounts (optional)** — sign in with Google (top-right) to **save commutes
  and places**. Saved commutes restore the full route + parameters in one
  click; saved places drop into From/To. The app works fully without an
  account (demo mode); sign-in only unlocks saving.

## Drawing the route on the map

The road route is fetched through the backend and cached:

- **No config needed:** with no key set, it uses the public **OSRM** demo
  server (fine for light/dev use, best-effort availability).
- **Recommended for real use:** set `OPENROUTESERVICE_API_KEY` (free tier,
  ~2,000 requests/day — sign up at https://openrouteservice.org/dev) for a
  reliable provider.
- Either way, the polyline is cached in Postgres (spatially, 30-day TTL), so
  repeat/near-identical routes are free and the stored geometry can seed future
  corridor/overlap analysis.

Map tiles are OpenStreetMap (no key). No Google Directions billing is involved.

## Accounts & sign-in (optional)

Sign-in uses Google Identity Services on the front end and verifies the ID
token server-side; no long-lived secret lives in the browser. To enable it:

1. In the [Google Cloud Console](https://console.cloud.google.com/apis/credentials),
   create an **OAuth 2.0 Client ID** of type *Web application*.
2. Add your app origin (e.g. `http://localhost:8900`) under *Authorized
   JavaScript origins*.
3. Set `GOOGLE_OAUTH_CLIENT_ID` in `.env` and restart.

The same Client ID is served to the SPA at runtime via `GET /api/config`, so
no rebuild is needed when you change it. Auth uses DRF tokens (returned on
login, stored client-side, sent as `Authorization: Token …`). **Sign in with
Apple** is scaffolded (`APPLE_OAUTH_CLIENT_ID`) but disabled pending an Apple
Developer account; leave it blank for now.
- **Analysis vector** — *Depart at* or *Arrive by*.
- **Hour range + interval** — e.g. 7 AM–9 AM every 15 minutes.
- **Days** — multi-select checkboxes, one trend line per day.
- **Color scheme** — Default, **Colorblind-safe (Okabe-Ito)**, or High
  contrast.
- The chart shows one line per day (typical duration) with a shaded
  **min–max confidence band**. Hover the legend to preview a day; click to pin
  the highlight (click again to clear). Tooltips show typical and range values
  for every day at that time.

## Notes & limitations

- **Predictions are for the next future occurrence** of each selected
  day/time (Google requires future departure times). Cached records are keyed
  by day-of-week, so they stay valid until the 7-day expiry.
- **"Arrive by" is an approximation**: the Distance Matrix API only supports
  arrival times for transit. The backend probes the typical duration once,
  then queries with `departure = arrival − duration`.
- **Logs are verbose by design**: `docker compose logs -f backend` shows every
  cache hit/miss and every Google request and response status.

## Testing & TDD

Everything runs in Docker — no local Python or Node needed:

```bash
make test            # full suite (backend + frontend)
make test-backend    # Django tests against real Postgres (incl. earthdistance SQL)
make test-frontend   # Vitest unit tests in the node build stage
```

Backend tests live in [backend/commute/tests/](backend/commute/tests/) and run
against a throwaway Postgres test database (with the real `earthdistance`
extension), so the spatial cache SQL is genuinely exercised. Google's HTTP
layer is mocked — tests never spend API calls. Coverage includes:

- **Cache rules** (`test_cache.py`): 1-mile radius hit/miss on both endpoints,
  exact day-of-week, ±4-minute delta, midnight wraparound, 7-day expiry,
  freshest-record-wins.
- **Analysis regressions** (`test_analysis.py`): `ZERO_RESULTS` routes must
  count their billed API calls; unreachable "arrive by" targets must shift to
  next week's occurrence; cache hits must make zero Google calls.
- **Google client** (`test_google_maps.py`): multi-candidate geocoding, region
  bias, key precedence (ENV > DB), min/max clamping across traffic models.
- **API endpoints** (`test_api.py`): setup/validation flows, geocode 409 vs
  candidates, analyze request validation, and cached-data-without-a-key.
- **Routing** (`test_routing.py`): OSRM/ORS provider selection, lat/lng
  conversion, spatial cache hit/miss, no-route errors.
- **Auth & saved data** (`test_auth_and_saved.py`): Google token verification
  (mocked), user creation/reuse, unverified-email rejection, and owner-scoped
  saved routes/addresses (users can't see or delete each other's data).

For TDD, watch mode: `docker compose run --rm frontend-test npm run test:watch`
for the frontend; for the backend re-run `make test-backend` (or
`docker compose run --rm backend python manage.py test commute.tests.test_cache`
for a single module).

## Frontend previews with recorded data (no API key / no API calls)

The cache can be seeded from CSV, so the full UI — chart, confidence bands,
day highlighting — works without spending a single Google API call:

```bash
make seed-demo    # loads backend/fixtures/demo_commute.csv (45 samples)
```

Then open the app, click **"Continue without a key"** on the setup screen (or
use your real key — cached points are served first either way) and run:

- From: `42.3550, -71.0656` (Boston Common)
- To: `42.3293, -71.1924` (Newton Centre)
- Depart at, 7 AM → 9 AM, **15 min** interval, days **Mon–Fri**

Every point is a cache hit (`0 Google API calls` in the result chips). The
fixture has a realistic rush-hour curve peaking ~8:15 AM with different
amplitudes per weekday. Imported rows are stamped with the load time, so they
stay cache-valid for 7 days — re-run `make seed-demo` to refresh.

To record your own real runs as a fixture:

```bash
make dump-cache > my_route.csv                 # export current cache
docker compose exec backend python manage.py load_cache fixtures/my_route.csv --replace
```

## Development (without Docker)

```bash
# Backend (needs a local Postgres with cube/earthdistance)
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@localhost:5432/commute
python manage.py migrate && python manage.py runserver

# Frontend (proxies /api to localhost:8000)
cd frontend
npm install
npm run dev
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Setup screen rejects key | Make sure Distance Matrix **and** Geocoding APIs are enabled and billing is on |
| `REQUEST_DENIED` during analysis | Same as above, or key restrictions block server-side use — allow the backend's IP or remove referer restrictions |
| Migration fails on Supabase with extension error | Enable `cube`/`earthdistance` in the Supabase dashboard, then `docker compose restart backend` |
| Port 8900 in use | Set `APP_PORT` in `.env` |
| Reset everything (including cache + stored key) | `docker compose down -v` |
