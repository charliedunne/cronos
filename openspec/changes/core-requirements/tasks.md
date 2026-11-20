# Tasks

## 1. Scaffolding

- [x] 1.1 Initialize the backend package: FastAPI app entry point, env-based configuration, pytest with httpx TestClient, and a `/healthz` endpoint — verify: `pytest` runs green including a smoke test hitting `/healthz`
- [x] 1.2 Add PostgreSQL connectivity (SQLAlchemy) and Alembic migration setup with an initial empty migration — verify: `alembic upgrade head` succeeds against the dev database defined in docker-compose.yml
- [x] 1.3 Initialize the frontend app (Vite + React + TypeScript) with a dev proxy to the backend API — verify: `npm run build` succeeds and the dev server serves the app

## 2. Authentication (user-auth)

- [x] 2.1 Add users and sessions tables via migration and ORM models — verify: `alembic upgrade head` applies and a test inserting a user row directly succeeds
- [x] 2.2 Implement Argon2id password hashing utility — verify: unit tests cover hash/verify round-trip and wrong-password rejection
- [x] 2.3 Implement login/logout endpoints with an httpOnly session cookie and a session-validation dependency for protected routes — verify: API tests show successful login sets the cookie, wrong credentials are rejected with 401 without revealing which part was invalid, requests without a valid session get 401, and logout revokes the session
- [x] 2.4 Implement admin-only account management endpoints (create, disable, re-enable) — verify: API tests show an admin can create an account that then logs in, duplicate username is rejected with 409, non-admin callers get 403, and a disabled account cannot log in
- [x] 2.5 Add a CLI command to seed the first administrator out-of-band — verify: running the command with provided credentials creates an admin user who can log in

## 3. Requirement store (requirement-store)

- [x] 3.1 Add modules and requirements tables via migration, including the req_no sequence and status/priority CHECK constraints — verify: `alembic upgrade head` applies and a test creating a module and requirement shows defaults "draft"/"medium" and the REQ- identifier format
- [x] 3.2 Implement module endpoints (create with unique name, rename, delete) — verify: API tests cover creation, duplicate name rejected with 409, rename to an existing name rejected, deleting a non-empty module rejected, and deleting an empty module succeeding
- [x] 3.3 Implement requirement create and browsing endpoints (list modules, list requirements of a module with attributes and lock state) — verify: API tests show created requirements return their identifier, identifiers stay unique and are never reused after deletion, and listings include all attributes
- [x] 3.4 Enforce attribute validation on create and update (non-empty title, status/priority enum values) — verify: API tests reject an empty title and invalid enum values with 422 and leave the requirement unchanged

## 4. Editing locks (editing-locks)

- [x] 4.1 Add the locks table via migration (requirement_id as primary key) — verify: `alembic upgrade head` applies and a test inserting a second lock row for the same requirement fails at the database level
- [x] 4.2 Implement lock/unlock endpoints (block, release by holder, admin force-release) — verify: API tests show locking an unlocked requirement records the holder, a second user's attempt is rejected with 409, release unlocks it, non-holders cannot release, and an admin can force-release any lock
- [x] 4.3 Enforce modification restriction: updating or deleting a requirement requires holding its lock — verify: API tests show updates without a lock are rejected, the holder's update succeeds and retains the lock, the holder's deletion removes the requirement with its identifier never reused, and non-holder updates are rejected
- [x] 4.4 Verify lock persistence across sessions and lock visibility in listings — verify: API test locks a requirement, revokes the session via logout, logs back in as the same user, and confirms the lock is still held and releasable; another user's module listing shows the lock state and holder

## 5. Frontend

- [x] 5.1 Build the login page and session handling (cookie auth, logout) — verify: in the dev environment, logging in as the seeded admin sets the cookie, a protected route loads, and logout returns to the login page
- [x] 5.2 Build the module list with create/rename/delete actions — verify: in the dev environment, creating a module makes it appear in the list and deleting a non-empty module shows an error instead of removing it
- [x] 5.3 Build the requirement list within a module plus a create form (title, text, status, priority) — verify: in the dev environment, a created requirement appears with its identifier and default values, and attribute edits persist after reload
- [x] 5.4 Build the lock UI: holder badge on locked rows, Block/Unblock actions, editing disabled for non-holders — verify: in the dev environment with two accounts, user A locking shows a badge to user B who cannot edit, and after A unlocks, B can lock and edit

## 6. Integration checks

- [x] 6.1 Add an end-to-end API test spanning auth → module → requirement → lock with two users — verify: the integration test passes, including the concurrent-lock conflict rejection
- [ ] 6.2 Write a README covering setup (database via docker-compose, migrations, seeding the first admin, running backend and frontend) — verify: following the README from a fresh clone reaches a working application

## Workflow follow-up

- Archive the change with `openspec archive core-requirements` once implementation is complete and verified, which merges the delta specs into openspec/specs/.
- Verify the archived result (specs present under openspec/specs/, change moved to changes/archive/).
