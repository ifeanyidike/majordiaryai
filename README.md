# Major Dairy AI

Dairy reproduction & herd-management platform — an Expo (React Native) mobile app
backed by a FastAPI + Supabase Postgres API. Tracks cows through their full
reproductive lifecycle (heat, insemination, needling protocols, pregnancy, dry,
calving, vaccination) and drives the daily technician/vet/farm workflows.

## Stack

- **Mobile:** Expo + expo-router, Zustand, TypeScript (repo root)
- **Backend:** FastAPI, SQLAlchemy (async), Alembic — in [`backend/`](backend/)
- **Data/Auth:** Supabase (Postgres + Auth). JWTs verified via JWKS (ES256).
- **Email:** SendGrid (optional; no-ops until a key is set)

## Layout

```
.                # Expo app (src/, app.json, eas.json, Makefile)
├─ src/          # screens, components, stores, theme
└─ backend/      # FastAPI app, migrations, scripts
```

## Prerequisites

- Node 18+ and npm
- Python 3.9 (a venv lives at `backend/.venv`)
- Xcode (iOS Simulator) and/or Android Studio (emulator)
- A Supabase project (Postgres + Auth)

## Setup

```bash
# 1. Environment — copy the examples and fill in your Supabase values
cp .env.example .env                  # Expo (public) env
cp backend/.env.example backend/.env  # backend secrets

# 2. Install deps (Python into backend/.venv + npm)
make install

# 3. Apply DB migrations
make migrate

# 4. (optional) Seed demo herd data — 3 farms, ~14 cows across the lifecycle
make seed

# 5. Run backend + Metro together (Ctrl-C stops both)
make dev
```

Backend runs on `http://localhost:8010`, Metro on `http://localhost:8081`.
In Metro press **i** (iOS), **a** (Android), or **w** (web).

> New accounts aren't linked to a farm on signup. Bootstrap your first admin /
> assign a technician with `scripts.link_user` (see Scripts below).

## Make targets

| Target | Does |
|---|---|
| `make dev` | Run backend + Metro together |
| `make backend` / `make frontend` | Run one side |
| `make ios` / `make android` | Open a simulator/emulator |
| `make migrate` | `alembic upgrade head` |
| `make seed` | Seed demo herd data |
| `make typecheck` | `tsc` + backend compile |
| `make stop` | Stop backend + Metro by port |

Override the port with `make dev BACKEND_PORT=8020` (keep `EXPO_PUBLIC_API_URL` in `.env` in sync).

## Scripts (run from `backend/`)

```bash
# Seed / reset the demo herd (idempotent)
.venv/bin/python -m scripts.seed

# Link an account to farms so role-scoping shows data:
.venv/bin/python -m scripts.link_user --email you@example.com --admin
.venv/bin/python -m scripts.link_user --email you@example.com --technician
.venv/bin/python -m scripts.link_user --email owner@example.com --farm-manager "Green Valley Dairy"
```

## Deployment

- **Backend → Render / Fly:** set the service root to `backend/`, provide the
  `backend/.env` values as secrets, and start with
  `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- **Mobile → EAS:** builds from the repo root (`eas build`). Set
  `EXPO_PUBLIC_API_URL` to the deployed backend URL. `eas update` ships JS-only
  changes over the air without a native rebuild.

## Notes

- The DB lives in Supabase (remote) — there's nothing to run locally.
- Email is off until `SENDGRID_API_KEY` is set; the app functions fully without it.
