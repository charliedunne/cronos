# Proposal

## Why

Cronos is a new collaborative requirements management application (in the spirit of DOORS and Polarion). The project is at a blank state: no code, no specs. This change establishes the foundation — user authentication plus a store of requirements organized in modules, with lock-based editing so multiple users can collaborate without live co-editing conflicts.

## What Changes

- Introduce a web application (FastAPI backend + React/TypeScript frontend) backed by PostgreSQL.
- Add user accounts with login/logout and session management.
- Add modules as top-level containers for requirements.
- Add requirements with a fixed attribute set (title, text, status, priority) and full create/read/update/delete support.
- Add lock-based editing: a user must block (lock) a requirement before editing it and unblock it afterwards; only the lock holder may modify a locked requirement.

## Capabilities

### New Capabilities

- `user-auth`: user accounts, credentials, login/logout, and session management for the collaborative web application.
- `requirement-store`: modules as top-level containers and requirements with a fixed attribute set (title, text, status, priority), including create, read, update, and delete operations.
- `editing-locks`: lock-based editing of requirements — block before edit, unblock after edit, with modification restricted to the lock holder.

### Modified Capabilities

(none — this is the first change)

## Impact

- New codebase: no existing code is affected.
- New backend service (Python/FastAPI) exposing a REST API for auth, modules, requirements, and locks.
- New frontend application (TypeScript/React) for browsing modules, viewing/editing requirements, and managing locks.
- New PostgreSQL database schema: users/sessions, modules, requirements, locks.
- No external system integrations in this change. Traceability links, baselines/version history, custom attribute sets, reporting, and import/export are explicitly out of scope and will be separate changes.
