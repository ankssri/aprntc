# Deploying aprntc (B1)

aprntc ships as a **single container**: a multi-stage build compiles the React
frontend, and FastAPI/uvicorn serves both the API and the static UI on one port.

## Quick start (Docker)
```bash
cp .env.example .env        # fill ARK_API_KEY, VIKINGDB_AK/SK, model ids
docker compose up --build   # → http://localhost:8000  (UI + API)
```
Persistent data (SQLite trajectory store, per-tenant namespaces, playbooks) lives in
the `aprntc-data` volume mounted at `/data`.

## What the image does
- **Stage 1 (node:22):** `npm install && npm run build` → `web/dist`.
- **Stage 2 (python:3.12):** `pip install -e '.[web,byteplus]'`, copies `web/dist`,
  sets `APRNTC_STATIC_DIR=/app/web/dist`, runs
  `uvicorn aprntc.web.app:app --host 0.0.0.0 --port 8000`.
- The final image has **no Node toolchain** (build artifacts only).

## Single-port serving (verified)
FastAPI serves everything on :8000 — no separate Vite in production:
- `/` and client-side routes (`/trajectories`, …) → the SPA (`index.html`)
- `/assets/*` → hashed static bundles
- `/api/*` → JSON API (never shadowed by the SPA fallback)
Local equivalent (no Docker):
```bash
cd web && npm run build && cd ..
APRNTC_STATIC_DIR=$PWD/web/dist .venv/bin/python -m uvicorn aprntc.web.app:app --port 8000
```

## Configuration (env)
- **Secrets:** `ARK_API_KEY`, `APRNTC_POLICY_MODEL`, `APRNTC_JUDGE_MODEL`, `VIKINGDB_AK`,
  `VIKINGDB_SK` (see `.env.example`). Provide via `--env-file`/compose `env_file`, never baked in.
- **`APRNTC_STATIC_DIR`** — path to the built frontend (set by the image; overridable).
- **`APRNTC_DB_URL`** — SQLite path; default `/data/aprntc.db` in the container.
- **Multi-tenancy (B2):** wire a `TenantResolver` in `AppState.from_env` (per-tenant data under
  the data root); external agents then authenticate with `X-API-Key` / `Bearer`.

## Production notes / follow-ups
- **State:** SQLite + JSON files on a volume is fine for a single instance. For scale/HA, swap
  the trajectory store to Postgres (B3) and put playbooks/tenants in a shared DB.
- **Process model:** one uvicorn worker by default. Add workers / a process manager (gunicorn -k
  uvicorn workers) once the store is Postgres-backed (SQLite + many writers needs care).
- **Scheduler:** nightly distillation isn't auto-run yet (B3) — trigger via cron/job for now.
- **TLS / ingress:** terminate TLS at your load balancer / reverse proxy in front of :8000.
