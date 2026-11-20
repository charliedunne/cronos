# editing-locks Specification

## Purpose

Lock-based editing for collaborative work without live co-editing: a user blocks an element before editing it and unblocks it afterwards, so at most one user edits a requirement at a time.

## Requirements

### Requirement: Acquiring a lock
The system SHALL allow any authenticated user to block (lock) a requirement that is not currently locked. A lock MUST record its holder.

#### Scenario: Lock an unlocked requirement
- **WHEN** an authenticated user blocks a requirement that no one has locked
- **THEN** the lock is granted and recorded with that user as holder

#### Scenario: Locked requirement cannot be locked again
- **WHEN** a user attempts to block a requirement already locked by another user
- **THEN** the system rejects the attempt and the original lock is unchanged

### Requirement: Lock state visibility
The system SHALL make each requirement's lock state and, when locked, its holder visible to all authenticated users.

#### Scenario: Other users see the lock
- **WHEN** a user locks a requirement and another user views the module
- **THEN** the second user sees that the requirement is locked and by whom

### Requirement: Modification restricted to lock holder
A user SHALL be able to modify or delete a requirement only while holding its lock. Attempts by non-holders MUST be rejected.

#### Scenario: Holder modifies a requirement
- **WHEN** the lock holder submits changes to a requirement's attributes
- **THEN** the changes are applied and the lock is retained

#### Scenario: Non-holder modification is rejected
- **WHEN** a user who does not hold the lock submits changes to a locked requirement
- **THEN** the system rejects the changes and the requirement is unchanged

### Requirement: Releasing a lock
The lock holder SHALL be able to unblock (release) a requirement at any time. After release, the requirement can be locked by any authenticated user.

#### Scenario: Release makes the requirement editable by others
- **WHEN** the lock holder releases a requirement
- **THEN** the requirement is unlocked and another user can immediately lock it

### Requirement: Lock persistence
A lock SHALL persist until explicitly released by its holder, including across the holder's sessions. A lock MUST NOT be lost when the holder logs out or their session ends.

#### Scenario: Lock survives logout
- **WHEN** a lock holder logs out and later logs back in
- **THEN** the lock is still held by that user and can be released by them

### Requirement: Administrative force release
An administrator SHALL be able to force-release any lock, regardless of its holder.

#### Scenario: Administrator releases a forgotten lock
- **WHEN** an administrator force-releases a lock held by another user
- **THEN** the requirement becomes unlocked and can be locked by any authenticated user
