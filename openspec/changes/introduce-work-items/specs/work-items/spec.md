# work-items Specification

## Purpose

The taxonomy layer for elements: administrators define the kinds of work items that exist (e.g., system-requirement, software-requirement, test-case) and the typed attributes each kind carries. Every element in a module is an instance of exactly one such type.

## ADDED Requirements

### Requirement: Work-item type management
An administrator SHALL be able to create, modify, and delete work-item types. Each type MUST have a name that is unique across all types. Deleting a type that still has work items of that type MUST be rejected.

#### Scenario: Administrator creates a type
- **WHEN** an administrator creates a work-item type with a unique name
- **THEN** the type exists and can be used to create work items

#### Scenario: Duplicate type name is rejected
- **WHEN** an administrator attempts to create or rename a type to a name already in use
- **THEN** the system rejects the operation

#### Scenario: Type with instances cannot be deleted
- **WHEN** an administrator attempts to delete a type that has work items
- **THEN** the system rejects the deletion and the type and its work items remain intact

### Requirement: Attribute definitions
Each work-item type SHALL define an ordered set of attributes. Each attribute MUST have a key that is unique within its type, a display label, and a data type drawn from the allowed set (string, text, integer, boolean, date, enum). An enum attribute MUST declare its allowed values. An attribute MAY be marked required and MAY declare a default value. The keys `title` and `id` are reserved for the mandatory system attributes and MUST NOT be used as type attribute keys.

#### Scenario: Define attributes for a type
- **WHEN** an administrator adds attributes with unique keys and valid data types to a type
- **THEN** the attributes are recorded in order and apply to work items of that type

#### Scenario: Duplicate attribute key is rejected
- **WHEN** an administrator attempts to add an attribute whose key already exists on the type
- **THEN** the system rejects the operation

#### Scenario: Invalid data type is rejected
- **WHEN** an administrator submits an attribute with a data type outside the allowed set, or an enum without allowed values
- **THEN** the system rejects the operation

### Requirement: Attribute ordering
Each attribute SHALL carry a position that determines its display order, and positions MUST be unique within a type. When an administrator omits the position, the system SHALL assign the next free position so the attribute is appended after the existing ones.

#### Scenario: Omitted position is auto-assigned
- **WHEN** an administrator adds an attribute without specifying a position
- **THEN** the system assigns it the next free position and it appears after the existing attributes

#### Scenario: Duplicate attribute position is rejected
- **WHEN** an administrator attempts to add or update an attribute with a position already used by another attribute on the same type
- **THEN** the system rejects the operation

### Requirement: Mandatory system attributes
Every work item SHALL carry two mandatory attributes that apply to all types regardless of their per-type definitions: a title (string, required, non-empty) and an identifier (system-assigned, stable, unique). The keys `title` and `id` MUST be reserved: an administrator MUST NOT be able to define a type attribute with either key.

#### Scenario: Every work item has a title and identifier
- **WHEN** a user creates a work item of any type with a non-empty title
- **THEN** the work item is stored with its title and a system-assigned identifier

#### Scenario: Empty title is rejected for any type
- **WHEN** a user attempts to create or update a work item of any type without a non-empty title
- **THEN** the system rejects the operation and the work item is unchanged

#### Scenario: Reserved attribute keys are rejected
- **WHEN** an administrator attempts to add a type attribute whose key is "title" or "id"
- **THEN** the system rejects the operation

### Requirement: Built-in default requirement type
The system SHALL provide a built-in work-item type named "requirement" whose per-type attributes are text (text), status (enum of draft/in-review/approved/deprecated, default draft), and priority (enum of low/medium/high, default medium). Together with the mandatory system attributes, a requirement work item presents title, text, status, and priority. The built-in type MUST NOT be deletable.

#### Scenario: Default type is present and protected
- **WHEN** an administrator lists work-item types
- **THEN** the built-in "requirement" type is present and attempting to delete it is rejected

### Requirement: Per-type attribute values
A work item SHALL store its mandatory title plus a value for each of its type's attributes, and every stored value MUST conform to the attribute's definition (data type, required-ness, and enum membership). Values that do not conform MUST be rejected.

#### Scenario: Conforming values are accepted
- **WHEN** a user provides attribute values that satisfy the type's definitions
- **THEN** the values are stored on the work item

#### Scenario: Non-conforming values are rejected
- **WHEN** a user omits a required value, supplies a value of the wrong data type, or uses an enum value not in the allowed set
- **THEN** the system rejects the operation and the work item is unchanged
