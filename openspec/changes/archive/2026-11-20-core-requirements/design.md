# Design

## Context

Blank repository; see proposal.md for motivation. Confirmed constraints: web app (server + browser), multi-user collaboration, lock-based editing with no live co-editing, PostgreSQL database, Python/FastAPI backend, TypeScript/React frontend.

## Goals / Non-Goals

**Goals:**
- Working foundation: authentication, modules, requirements with a fixed attribute set, lock-based editing
- A clean API and schema that later changes (traceability links, baselines, custom attributes) can extend without rework
- Lock exclusivity guaranteed by the database, not by application-level coordination

**Non-Goals:**
- Traceability links, baselines/version history, custom attribute sets, reporting, import/export (later changes)
- Permission granularity beyond administrator vs. regular user
- Live co-editing of any kind
- High availability or clustering; a single-node deployment is sufficient

## Decisions

### D1: Architecture — FastAPI REST API + React SPA
The backend exposes a versioned JSON REST API under `/api/v1`; the built React SPA is served as static files by the same process in production.
Alternatives considered: server-rendered pages (rejected — data-heavy UIs with tables and lock badges are better served by an SPA, and it keeps the door open for richer client behavior later); microservices (rejected — overkill for a single-team tool).

### D2: Session-based auth with opaque tokens stored in PostgreSQL
Login creates a session row (opaque random token, user id, created at, revoked at) and returns it as an httpOnly, Secure, SameSite=Lax cookie. Every API request validates the session against the database; logout or account disablement revokes it immediately.
Alternatives considered: stateless JWT (rejected — no server-side revocation; a logged-out or disabled user would remain valid until token expiry); SSO/OAuth providers (deferred — can be added later as an additional login method without changing this design).

### D3: Passwords hashed with Argon2id
Argon2id via `argon2-cffi`, parameters at current OWASP-recommended minimums.
Alternatives considered: bcrypt (acceptable, but Argon2 is the newer recommendation); anything weaker is not an option.

### D4: Database schema
- `users(id, username UNIQUE, password_hash, is_admin, is_active, created_at)`
- `sessions(token PK, user_id FK, created_at, revoked_at NULL)`
- `modules(id, name UNIQUE, created_by FK users, created_at)`
- `requirements(id, module_id FK, req_no UNIQUE, title, text, status CHECK, priority CHECK, created_by FK, created_at, updated_at)`
- `locks(requirement_id PK/FK, holder_id FK users, locked_at)`

Requirement identifiers are globally unique, human-readable values ("REQ-" + zero-padded number) drawn from a PostgreSQL sequence; the sequence only advances, so deleted identifiers are never reused.
Alternatives considered: per-module numbering (rejected — identifiers must stay stable and unambiguous tool-wide, as in DOORS); UUIDs (rejected — poor ergonomics in a domain where humans cite requirement IDs constantly).

### D5: Lock exclusivity enforced by the database
`locks.requirement_id` is the primary key of the locks table: a second concurrent INSERT fails with a unique violation, which the API maps to HTTP 409 Conflict. No check-then-set in application code, no advisory locks — atomicity comes from the constraint.
Alternatives considered: a nullable `locked_by` column on requirements (equally viable; a separate table was chosen to keep requirements clean and leave room for lock history/audit later); optimistic concurrency tokens (insufficient — we need explicit block/unblock semantics, not last-write-wins).

### D6: Frontend — React + TanStack Query
Server state (modules, requirements, locks) is managed with TanStack Query; mutations invalidate the affected queries so lock states stay fresh as other users act. The requirement list shows a holder badge on locked rows plus Block/Unblock actions.
Alternatives considered: Redux for server state (rejected — a query cache does that job with less code); WebSocket push for live lock updates (deferred — refetch-on-focus and post-mutation invalidation are sufficient for v1).

## Risks / Trade-offs

- [A forgotten lock blocks a requirement indefinitely] → administrator force-release is spec'd; lock expiry or reminders deferred to a later change
- [No fine-grained permissions in v1 — any authenticated user can edit anything that is unlocked] → acceptable for the foundation; a roles/permissions model is a later change
- [Requirement deletion is irreversible in v1] → deletion requires holding the lock (a deliberate act); baselines/version history in a later change will add recovery
- [Session validation hits PostgreSQL on every request] → a single indexed lookup; fine at expected scale, cacheable in Redis if it ever matters
- [Status/priority enum values are fixed by this change] → sensible defaults chosen now; changing them later is a MODIFIED spec plus a data migration

## Migration Plan

Greenfield — no existing data.
1. Apply schema migrations (Alembic) on first start.
2. Provision the first administrator out-of-band via a CLI command (credentials from environment or prompt) — required because account creation is admin-only.
3. Deploy backend + built SPA. Rollback: redeploy the previous artifact (none exists yet, so initially just stop using it).

## Open Questions

(none — both resolved with the user: no lock expiry in v1, admin force-release only; enum defaults confirmed as status {draft, in-review, approved, deprecated} and priority {low, medium, high})
