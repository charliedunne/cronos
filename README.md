# Cronos

A work-item management application: modules contain work items of
administrator-defined types, each with a stable identifier and its own set of
attributes. Every work item carries a mandatory title; identifiers are
assigned by the system as `<TYPE_PREFIX>-<sequence>` (e.g. `REQ-00012`).
Editing is protected by per-item locks — a user must block (lock) an item
before modifying or deleting it, so concurrent editors cannot clobber each
other's work.

Administrators manage the type registry from the "Types" page: create types
with an id prefix and attribute definitions (string, text, integer, boolean,
date, enum), edit or remove them, and set per-attribute required flags,
defaults, and enum options. A built-in `requirement` type (prefix `REQ`) with
text/status/priority attributes is seeded on first migration and cannot be
deleted.

## Stack

| Layer    | Technology                                                        |
| -------- | ----------------------------------------------------------------- |
| Backend  | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL — Python ≥ 3.14, `uv`  |
| Frontend | React 19, Vite, TypeScript, react-router-dom, TanStack Query      |
| Database | PostgreSQL 17 (Docker or local)                                   |

## Prerequisites

- Python 3.14+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ (or 22.12+) with npm
- Docker **or** a locally installed PostgreSQL server (see below)

## Setup

### 1. Database

Start the database from the repository root:

```sh
docker compose up -d db
```

This runs PostgreSQL 17 on port 5432 with role `cronos`, password `cronos`,
and database `cronos` (data persisted in the `pgdata` volume).

<details>
<summary>No Docker? Use the local-cluster helper</summary>

On machines without Docker, a private user-managed PostgreSQL cluster can be
started instead (idempotent; needs the `postgresql` binaries installed):

```sh
scripts/dev-db.sh
```

It creates a cluster under `~/.cronos/pgdata`, starts it on port 5432, and
provisions the same `cronos` role and database.
</details>

### 2. Backend

From the `backend/` directory:

```sh
cd backend
uv sync
```

Create a local `.env` (gitignored). For plain-HTTP development the session
cookie must not carry the `Secure` flag, or browsers will refuse to send it:

```sh
cat > .env <<'EOF'
CRONOS_COOKIE_SECURE=false
EOF
```

Apply the schema migrations:

```sh
uv run alembic upgrade head
```

### 3. Seed the first administrator

Account creation over the API is admin-only, so the very first admin is
provisioned out-of-band with the CLI (values come from flags, then
`CRONOS_ADMIN_USERNAME` / `CRONOS_ADMIN_PASSWORD`, then interactive prompts):

```sh
uv run python -m app.cli seed-admin --username admin --password '<choose a password>'
```

The command refuses to overwrite an existing user.

### 4. Run the backend

```sh
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API is served under `/api/v1`; a liveness probe is available at
`GET /healthz`.

### 5. Run the frontend

From the `frontend/` directory, in a second terminal:

```sh
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> and log in with the admin account from step 3.
The Vite dev server proxies `/api` to the backend on port 8000, so no extra
configuration is needed.

## Configuration

Backend settings are read from environment variables prefixed with `CRONOS_`
or from `backend/.env`:

| Variable                | Default                                                | Purpose                                            |
| ----------------------- | ------------------------------------------------------ | -------------------------------------------------- |
| `CRONOS_DATABASE_URL`   | `postgresql+psycopg://cronos:cronos@localhost:5432/cronos` | SQLAlchemy database URL                          |
| `CRONOS_COOKIE_SECURE`  | `true`                                                 | `Secure` flag on the session cookie (set `false` for plain-HTTP development) |

## Tests

The backend test suite runs against a live database (it uses the configured
`CRONOS_DATABASE_URL`, so start the database first):

```sh
cd backend
uv run pytest
```
