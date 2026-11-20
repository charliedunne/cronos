# Design

Generalize the single `Requirement` model into a typed **work item** model backed by an admin-managed type registry, while preserving existing behavior for the built-in requirement type and keeping stable identifiers.

## Decisions

### D1 — Generalize `Requirement` → `WorkItem`; keep one global sequence
Rename the element table to `work_items`. Keep a single monotonically increasing sequence (`requirement_req_no_seq`) so identifiers stay stable, unique, and never reused across all types. The human-readable identifier is rendered as `<TYPE_PREFIX>-<zero-padded seq>`, where `TYPE_PREFIX` is part of the type definition (the built-in requirement type uses `REQ`, preserving today's `REQ-000042` form). A work item's type is set at creation and is **immutable** — changing it would orphan attribute values.

### D2 — Attribute storage: mandatory system attributes + first-class `title` + JSONB `attributes`
Every work item carries two **mandatory system attributes** regardless of type: `title` (string, required, non-empty) and the identifier (system-assigned per D1). Keep `title` as a first-class, non-nullable, indexed column — it is the primary display field on all types; keeping it first-class preserves existing queries and indexes. Store all other attribute values in a single `attributes` JSONB column keyed by the attribute definition's key. For the built-in requirement type, `text`, `status`, and `priority` therefore live inside `attributes`. The keys `title` and `id` are reserved: they cannot be used as per-type attribute-definition keys.

Rationale: an EAV table would complicate every read/write for a schema that is dynamic per type; JSONB is idiomatic on PostgreSQL 17 and matches the type-driven model. Conformance to a type's attribute definitions (data type, required-ness, enum membership), the mandatory non-empty title on all types, and reserved-key rejection are enforced in the API layer via a validation service; a DB trigger can be added later if needed.

### D3 — Type and attribute-definition models
- `WorkItemType`: `id`, `name` (unique), `description`, `id_prefix`, `is_builtin` (built-in types cannot be deleted or renamed), `created_at`.
- `AttributeDefinition`: `id`, `type_id` (FK, CASCADE), `key` (unique within a type via `(type_id, key)` constraint; MUST NOT be a reserved system key — `title`, `id`), `label`, `data_type` (enum: string/text/integer/boolean/date/enum), `options` (JSONB list; required for enum), `required` (bool), `default_value` (JSONB, nullable), `position` (int, display order; unique within a type via `(type_id, position)` constraint — an omitted position is auto-assigned to the next free value so the attribute is appended after the existing ones).

### D4 — Deletion and rename safety
Deleting a type that has work items is rejected (enforced transactionally before the DELETE). Renaming a type or its `id_prefix` affects only **newly created** work items; existing identifiers are never rewritten (identifiers are stable). The built-in requirement type cannot be deleted.

### D5 — Data migration
A single Alembic revision: create `work_item_types` and `attribute_definitions`; rename `requirements` → `work_items`, add `type_id` and `attributes` JSONB; seed the built-in "requirement" type with title/text/status/priority definitions; copy each existing requirement's text/status/priority into its `attributes` map and set `type_id` to the built-in type; retarget the `locks` foreign key from `requirements.id` to `work_items.id`. Existing `req_no`/identifiers are preserved.

### D6 — API shape (breaking)
- New router under `/api/v1/work-item-types` for types and their attribute definitions. Mutations (create/modify/delete of types and attributes) are admin-only; **listing is open to any authenticated user** because the element-creation UI needs the type catalog (names, id prefixes, attribute definitions) to render its dynamic form.
- Element endpoints generalize: `GET/POST /api/v1/modules/{module_id}/work-items`, `GET/PATCH/DELETE /api/v1/work-items/{id}`. The old `/requirements` paths are removed in v1 (documented breaking change).
- Lock endpoints generalize to work items (`.../work-items/{id}/lock`), preserving acquire/release/force-release/persistence behavior.

### D7 — Frontend
Type selector on element creation; a dynamic attribute form rendered from the type's definitions (string→input, text→textarea, integer→number, boolean→checkbox, date→date input, enum→select); module detail renders each item's title, a type badge, its attribute values, and lock state; a new admin "Work Item Types" page for managing types and attributes.

## Risks / Trade-offs
- **App-level validation only**: JSONB has no DB-level type constraints, so per-type validation lives in the API. Mitigate with a single validation service, a clear error contract, and tests covering each data type and failure mode; add a DB trigger later if stricter enforcement is wanted.
- **Type deletion protection** must be checked and applied in one transaction to avoid races.
- **Live-data migration**: run against a copy of production-shaped data first; the revision must be idempotent-safe and reversible where practical.
- **Breaking API rename**: coordinate frontend + backend in the same change so the app stays consistent; document for any external consumers.
