# Proposal

## Why

Cronos's foundation models exactly one kind of element — a "requirement" with a fixed attribute set (title, text, status, priority). A requirements-management tool in the spirit of DOORS or Polarion works with many kinds of elements: system requirements, software requirements, test cases, and more, each carrying its own attributes. Today there is no way to represent a test case, to distinguish a system requirement from a software requirement, or to give different element kinds their own fields — everything is the same flat record. This change generalizes the element model into typed **work items** so the tool can grow beyond a single requirement type without re-architecting storage, editing, or the API.

## What Changes

- Introduce a **work item** as the general element: every element contained in a module is a work item of a specific **type**.
- Add an **admin-managed work-item type registry**: administrators define, modify, and delete work-item types. Each type has a unique name and an ordered set of typed **attribute definitions** (e.g., string, text, integer, boolean, date, enum/select).
- Each work item stores **per-type attribute values** that are validated against its type's attribute definitions at creation and update.
- Every work item carries **mandatory system attributes** — a non-empty title and a system-assigned identifier — that apply to all types; the keys `title` and `id` are reserved from per-type attribute definitions.
- Provide a **built-in default requirement type** carrying the current core attributes (title, text, status, priority) so existing data and behavior are preserved.
- **BREAKING**: The `Requirement` model is generalized to a `WorkItem`. Element endpoints now operate on work items and require a type; the previously fixed attribute set becomes type-driven. Behavior for the built-in requirement type is unchanged.
- Generalize lock-based editing so any work item (of any type) can be locked, not only requirements.
- Migrate existing requirement rows into work items of the default requirement type via a data migration.

## Capabilities

### New Capabilities
- `work-items`: The admin-managed work-item type registry and per-type attribute definitions — the taxonomy that classifies work items (system-requirement, software-requirement, test-case, …) and defines each type's typed attribute set, including a built-in default requirement type.

### Modified Capabilities
- `requirement-store`: Modules now contain work items of any type. Element creation selects a type and validates attributes against that type's definitions; browsing exposes each item's type and per-type attribute values alongside the existing lock state. Module management (create/rename/delete, non-empty protection) is unchanged.
- `editing-locks`: Locks apply to work items of any type rather than only requirements. All acquire / release / holder-only-modify / persistence / force-release behavior generalizes from "requirement" to "work item."

## Impact

- **Backend**: New models (`WorkItem`, `WorkItemType`, `AttributeDefinition`, per-type attribute values) and Alembic migration(s) including a data migration of existing requirements. A new admin router for type/attribute management. The modules, requirements, and locks routers generalize to work items. API stays under `/api/v1`.
- **Frontend**: Type selector on element creation, a dynamic per-type attribute form, an admin page for managing types and their attributes, and the module detail view updated to render arbitrary work-item attributes and lock state.
- **Tests**: Extend the backend suite with type-registry CRUD, per-type attribute validation, and migration coverage; update the end-to-end two-user flow to use work items.
