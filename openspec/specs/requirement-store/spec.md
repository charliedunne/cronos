# requirement-store Specification

## Purpose

Storage and organization of requirements: modules serve as top-level containers holding requirements with a fixed attribute set of title, text, status, and priority.

## Requirements

### Requirement: Module management
The system SHALL allow any authenticated user to create, rename, and delete modules. Each module MUST have a name that is unique among all modules. Deleting a module that still contains requirements MUST be rejected.

#### Scenario: Create a module
- **WHEN** an authenticated user creates a module with a unique name
- **THEN** the module exists and can hold requirements

#### Scenario: Duplicate module name is rejected
- **WHEN** an authenticated user attempts to create or rename a module to a name already in use
- **THEN** the system rejects the operation

#### Scenario: Non-empty module cannot be deleted
- **WHEN** an authenticated user attempts to delete a module that contains requirements
- **THEN** the system rejects the deletion and the requirements remain intact

### Requirement: Requirement creation
The system SHALL allow any authenticated user to create a requirement within a module by providing a title and text. The system SHALL assign each requirement a stable, unique identifier that never changes and is never reused. New requirements SHALL default to status "draft" and priority "medium".

#### Scenario: Create a requirement
- **WHEN** an authenticated user creates a requirement in a module with a title and text
- **THEN** the requirement appears in the module with its assigned identifier, status "draft", and priority "medium"

#### Scenario: Identifiers are stable and unique
- **WHEN** requirements are created over time, including after other requirements have been deleted
- **THEN** no two existing requirements share an identifier and an identifier is never reassigned to a different requirement

### Requirement: Requirement attributes
Each requirement SHALL have the attributes title (required, non-empty), text, status, and priority. Status SHALL be one of "draft", "in-review", "approved", or "deprecated". Priority SHALL be one of "low", "medium", or "high".

#### Scenario: Invalid attribute values are rejected
- **WHEN** a user submits an empty title, or a status or priority value outside the allowed sets
- **THEN** the system rejects the operation and the requirement is unchanged

### Requirement: Requirement browsing
The system SHALL allow any authenticated user to list all modules and to list the requirements of a module, including each requirement's identifier, attributes, and current lock state.

#### Scenario: List modules
- **WHEN** an authenticated user requests the module list
- **THEN** the system returns all modules with their names

#### Scenario: List requirements of a module
- **WHEN** an authenticated user opens a module
- **THEN** the system returns its requirements with identifier, title, text, status, priority, and lock state

### Requirement: Requirement deletion
The system SHALL allow the holder of a requirement's lock to delete the requirement. Deletion removes the requirement from its module; its identifier MUST never be reused.

#### Scenario: Lock holder deletes a requirement
- **WHEN** the lock holder of a requirement requests its deletion
- **THEN** the requirement is removed from the module and its identifier is never assigned again
