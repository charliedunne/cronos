# Tasks

## 1. Data model & migration
- [x] 1.1 Add `WorkItem`, `WorkItemType`, and `AttributeDefinition` models; generalize `Requirement` → `WorkItem` (first-class `title`, JSONB `attributes`, `type_id`).
- [x] 1.2 Create the Alembic revision: new tables, seed the built-in "requirement" type + attribute definitions, migrate existing requirements into work items of that type (text/status/priority → `attributes`), retarget the `locks` FK to `work_items.id`.
- [x] 1.3 Update ORM relationships and identifier rendering (`<TYPE_PREFIX>-<zero-padded seq>` from the global sequence).

## 2. Backend API — type registry (admin)
- [x] 2.1 Admin router: create/modify/delete work-item types (name uniqueness, non-empty deletion protection, built-in protection).
- [x] 2.2 Attribute-definition CRUD within a type (key uniqueness, reserved keys `title`/`id` rejected, data-type validation, enum options, required/default, ordering).
- [x] 2.3 Validation service: validate a set of attribute values against a type's definitions (data type, required-ness, enum membership) plus the mandatory non-empty title for all types, with a clear error contract.

## 3. Backend API — work items
- [x] 3.1 Generalize element creation to select a type and validate attributes; assign the stable identifier.
- [x] 3.2 Generalize update (lock-holder only) to validate per-type attribute values.
- [x] 3.3 Generalize browsing: list a module's work items with type, attribute values, and lock state.
- [x] 3.4 Generalize deletion (lock-holder only); identifier never reused.

## 4. Backend API — locks generalization
- [x] 4.1 Retarget lock endpoints from requirement to work item; preserve acquire/release/force-release/persistence behavior.

## 5. Tests
- [x] 5.1 Type-registry CRUD tests (create, duplicate name, delete empty, delete non-empty, built-in protection, reserved-key rejection).
- [x] 5.2 Per-type attribute validation tests (valid value, missing required, wrong data type, invalid enum, empty title on a custom type).
- [x] 5.3 Migration test: existing requirements become work items of the default type with attributes preserved and identifiers unchanged.
- [x] 5.4 Update the end-to-end two-user flow to use work items, including a non-requirement type (e.g., test-case) to prove generalization.

## 6. Frontend
- [x] 6.1 Update the API client and TypeScript types for work items, types, and attribute definitions.
- [x] 6.2 Type selector on element creation + dynamic per-type attribute form.
- [x] 6.3 Module detail renders arbitrary work-item attributes, a type badge, and lock state.
- [x] 6.4 Admin "Work Item Types" page (CRUD types and their attribute definitions).

## 7. Docs
- [x] 7.1 Update the README to reflect work items, types, and the admin type-management flow.

## 8. Follow-up: unique attribute positions
- [x] 8.1 Update the work-items spec and design notes: position is unique per type; an omitted position is auto-assigned (append).
- [x] 8.2 Model + migration 0006: renumber existing duplicate positions per type, add `(type_id, position)` unique constraint.
- [x] 8.3 API: auto-assign omitted positions on create; reject colliding positions with a clear 409 on create and update (omitted position on update leaves it unchanged).
- [x] 8.4 Tests for auto-assignment and collision rejection (including the migration renumbering); frontend suggests the next free position.
