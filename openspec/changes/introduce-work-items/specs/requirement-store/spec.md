# requirement-store Specification

## MODIFIED Requirements

### Requirement: Requirement creation
The system SHALL allow any authenticated user to create a work item within a module by choosing a work-item type and providing a non-empty title plus that type's attribute values. A work item's type SHALL be set at creation and MUST NOT change afterwards. The system SHALL assign each work item a stable, unique identifier that never changes and is never reused. A work item of the built-in requirement type defaults its status to "draft" and priority to "medium".

#### Scenario: Create a requirement
- **WHEN** an authenticated user creates a requirement in a module with a title and text
- **THEN** the requirement appears in the module with its assigned identifier, status "draft", and priority "medium"

#### Scenario: Identifiers are stable and unique
- **WHEN** requirements are created over time, including after other requirements have been deleted
- **THEN** no two existing requirements share an identifier and an identifier is never reassigned to a different requirement

#### Scenario: Create a work item of a custom type
- **WHEN** an authenticated user creates a work item in a module by selecting a non-built-in type and supplying a non-empty title and that type's attribute values
- **THEN** the work item appears in the module with its assigned identifier, its selected type, and the supplied attribute values

### Requirement: Requirement attributes
A work item's attributes SHALL consist of the mandatory system attributes — title (required, non-empty) and identifier — plus those defined by its type. For the built-in requirement type the per-type attributes are text, status, and priority; status SHALL be one of "draft", "in-review", "approved", or "deprecated" and priority SHALL be one of "low", "medium", or "high".

#### Scenario: Invalid attribute values are rejected
- **WHEN** a user submits an empty title, or a status or priority value outside the allowed sets
- **THEN** the system rejects the operation and the requirement is unchanged

### Requirement: Requirement browsing
The system SHALL allow any authenticated user to list all modules and to list the work items of a module, including each work item's identifier, its type, its attribute values, and its current lock state.

#### Scenario: List modules
- **WHEN** an authenticated user requests the module list
- **THEN** the system returns all modules with their names

#### Scenario: List requirements of a module
- **WHEN** an authenticated user opens a module
- **THEN** the system returns its requirements with identifier, title, text, status, priority, and lock state

#### Scenario: List work items of a module
- **WHEN** an authenticated user opens a module that contains work items of different types
- **THEN** the system returns all its work items, each with identifier, type, attribute values, and lock state

### Requirement: Requirement deletion
The system SHALL allow the holder of a work item's lock to delete the work item. Deletion removes the work item from its module; its identifier MUST never be reused.

#### Scenario: Lock holder deletes a requirement
- **WHEN** the lock holder of a requirement requests its deletion
- **THEN** the requirement is removed from the module and its identifier is never assigned again
