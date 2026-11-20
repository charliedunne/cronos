# editing-locks Specification

## MODIFIED Requirements

### Requirement: Acquiring a lock
The system SHALL allow any authenticated user to block (lock) a work item that is not currently locked, regardless of its type. A lock MUST record its holder.

#### Scenario: Lock an unlocked requirement
- **WHEN** an authenticated user blocks a requirement that no one has locked
- **THEN** the lock is granted and recorded with that user as holder

#### Scenario: Locked requirement cannot be locked again
- **WHEN** a user attempts to block a requirement already locked by another user
- **THEN** the system rejects the attempt and the original lock is unchanged

#### Scenario: Lock an unlocked work item of any type
- **WHEN** an authenticated user blocks a work item of a non-built-in type that no one has locked
- **THEN** the lock is granted and recorded with that user as holder

### Requirement: Lock state visibility
The system SHALL make each work item's lock state and, when locked, its holder visible to all authenticated users.

#### Scenario: Other users see the lock
- **WHEN** a user locks a requirement and another user views the module
- **THEN** the second user sees that the requirement is locked and by whom

### Requirement: Modification restricted to lock holder
A user SHALL be able to modify or delete a work item only while holding its lock. Attempts by non-holders MUST be rejected.

#### Scenario: Holder modifies a requirement
- **WHEN** the lock holder submits changes to a requirement's attributes
- **THEN** the changes are applied and the lock is retained

#### Scenario: Non-holder modification is rejected
- **WHEN** a user who does not hold the lock submits changes to a locked work item
- **THEN** the system rejects the changes and the work item is unchanged

### Requirement: Releasing a lock
The lock holder SHALL be able to unblock (release) a work item at any time. After release, the work item can be locked by any authenticated user.

#### Scenario: Release makes the requirement editable by others
- **WHEN** the lock holder releases a requirement
- **THEN** the requirement is unlocked and another user can immediately lock it
