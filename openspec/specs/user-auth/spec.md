# user-auth Specification

## Purpose

Authentication and session management for the collaborative application: users have accounts with credentials, log in to obtain a session, and act only while authenticated.

## Requirements

### Requirement: User account management
The system SHALL allow an administrator to create user accounts with a unique username and a password, and to disable or re-enable accounts. Creating an account with an already existing username MUST be rejected.

#### Scenario: Administrator creates an account
- **WHEN** an administrator creates a new account with a unique username and password
- **THEN** the account is created and the user can log in with those credentials

#### Scenario: Duplicate username is rejected
- **WHEN** an administrator attempts to create an account whose username already exists
- **THEN** the system rejects the request and no account is created

#### Scenario: Disabled account cannot log in
- **WHEN** a user with a disabled account attempts to log in with valid credentials
- **THEN** the system rejects the login

### Requirement: Login
The system SHALL authenticate a user who provides a valid username and password, and reject any other combination.

#### Scenario: Successful login
- **WHEN** a user submits correct credentials for an active account
- **THEN** the system authenticates the user and establishes a session

#### Scenario: Invalid credentials are rejected
- **WHEN** a user submits a wrong password or an unknown username
- **THEN** the system rejects the login without revealing which part was invalid

### Requirement: Session management
The system SHALL associate authenticated requests with a session that remains valid until the user logs out. Requests without a valid session MUST be rejected.

#### Scenario: Authenticated request succeeds
- **WHEN** a user makes an API request while holding a valid session
- **THEN** the request is processed as that user

#### Scenario: Unauthenticated request is rejected
- **WHEN** a request is made without a session, or with a revoked or expired session
- **THEN** the system rejects the request with an authentication error

#### Scenario: Logout terminates the session
- **WHEN** a user logs out
- **THEN** the session is invalidated and subsequent requests using it are rejected
