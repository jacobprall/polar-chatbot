# Requirements Document

## Introduction

The Polar Prompt Tester is a Streamlit-based application designed to help engineers at Oso determine the optimal prompting strategies for guiding different language models in generating Polar (Domain Specific Language) code from user requirements documents. The application provides a complete workflow for testing, validating, and iterating on Polar code generation, with session management and flexible storage options.

## Requirements

### Requirement 1

**User Story:** As an Oso engineer, I want to create and manage test sessions, so that I can organize my Polar code generation experiments and track different prompting strategies.

#### Acceptance Criteria

1. WHEN a user accesses the application THEN the system SHALL display an option to create a new test session
2. WHEN a user creates a new test session THEN the system SHALL generate a unique session identifier and initialize session storage
3. WHEN a user wants to review previous work THEN the system SHALL display a list of existing sessions with creation dates and session names
4. WHEN a user selects an existing session THEN the system SHALL load all session data including requirements, generated code, validation results, and notes
5. IF a session contains previous data THEN the system SHALL restore the complete session state including all tabs and components

### Requirement 2

**User Story:** As an Oso engineer, I want to input and edit user requirements text, so that I can provide clear specifications for Polar code generation.

#### Acceptance Criteria

1. WHEN a user is in an active session THEN the system SHALL provide a text editor component for requirements input
2. WHEN a user types in the text editor THEN the system SHALL automatically save changes to the current session
3. WHEN a user wants to import requirements THEN the system SHALL provide an option to upload text files
4. WHEN a user uploads a requirements file THEN the system SHALL load the content into the text editor and save it to the session
5. IF the requirements text exceeds reasonable limits THEN the system SHALL display appropriate warnings about content length

### Requirement 3

**User Story:** As an Oso engineer, I want to generate Polar code from requirements and view the results, so that I can evaluate the effectiveness of different prompting strategies.

#### Acceptance Criteria

1. WHEN a user has entered requirements text THEN the system SHALL provide a "Generate" button to trigger code generation
2. WHEN a user clicks the Generate button THEN the system SHALL send the requirements to the configured language model with the current prompting strategy
3. WHEN code generation completes THEN the system SHALL display the generated Polar code in a separate tab component
4. WHEN code generation fails THEN the system SHALL display error messages and allow the user to retry
5. IF multiple generations are performed in a session THEN the system SHALL maintain a history of all generated code versions

### Requirement 4

**User Story:** As an Oso engineer, I want to validate generated Polar code using the oso-cloud CLI, so that I can verify the correctness and syntax of the generated code.

#### Acceptance Criteria

1. WHEN Polar code is generated THEN the system SHALL automatically trigger validation using the oso-cloud CLI package
2. WHEN validation completes successfully THEN the system SHALL display a success indicator with validation details
3. WHEN validation fails THEN the system SHALL display the specific error messages returned by the oso-cloud CLI
4. WHEN validation fails THEN the system SHALL provide a "Retry" button to attempt code regeneration with error context
5. IF the oso-cloud CLI is not available THEN the system SHALL display appropriate error messages and guidance

### Requirement 5

**User Story:** As an Oso engineer, I want to retry code generation with error feedback, so that I can iteratively improve the generated Polar code based on validation failures.

#### Acceptance Criteria

1. WHEN validation fails and user clicks Retry THEN the system SHALL include the error message and previously generated code in the next LLM request
2. WHEN retry generation completes THEN the system SHALL automatically validate the new code and display results
3. WHEN multiple retries occur THEN the system SHALL maintain a complete history of attempts, errors, and improvements
4. WHEN retry validation succeeds THEN the system SHALL clearly indicate the successful resolution
5. IF retry attempts exceed a reasonable limit THEN the system SHALL suggest manual intervention or different approaches

### Requirement 6

**User Story:** As an Oso engineer, I want to add and review notes for each session, so that I can document insights, observations, and conclusions about different prompting strategies.

#### Acceptance Criteria

1. WHEN a user is in an active session THEN the system SHALL provide a notes section for free-form text input
2. WHEN a user adds notes THEN the system SHALL automatically save the notes to the session storage
3. WHEN a user reviews an old session THEN the system SHALL display all previously saved notes
4. WHEN a user edits existing notes THEN the system SHALL preserve the edit history with timestamps
5. IF notes become lengthy THEN the system SHALL provide appropriate formatting and organization options

### Requirement 7

**User Story:** As an Oso engineer, I want flexible storage options for my sessions, so that I can work locally or collaborate using cloud storage.

#### Acceptance Criteria

1. WHEN the application starts THEN the system SHALL support both local file storage and S3-compatible cloud storage
2. WHEN using local storage THEN the system SHALL store session data in a structured local directory
3. WHEN using S3 storage THEN the system SHALL authenticate and store session data in the configured S3 bucket
4. WHEN switching between storage backends THEN the system SHALL provide migration utilities to transfer existing sessions
5. IF storage operations fail THEN the system SHALL provide clear error messages and fallback options

### Requirement 8

**User Story:** As an Oso engineer, I want the storage interface to be modular and S3-compliant, so that I can easily switch between different storage backends without changing application logic.

#### Acceptance Criteria

1. WHEN the system performs storage operations THEN it SHALL use a consistent interface regardless of the backend
2. WHEN implementing new storage backends THEN they SHALL conform to the S3-compatible interface specification
3. WHEN the application reads or writes data THEN it SHALL use the same API calls for both local and cloud storage
4. WHEN storage configuration changes THEN the system SHALL seamlessly switch backends without data loss
5. IF a storage backend becomes unavailable THEN the system SHALL gracefully handle errors and suggest alternatives

### Requirement 9

**User Story:** As an Oso engineer, I want to use an append-only event log for session metadata, so that I can maintain a complete audit trail of all testing activities and rebuild session state from events.

#### Acceptance Criteria

1. WHEN any session activity occurs THEN the system SHALL create an event record with timestamp, user, document_id, version, and event type
2. WHEN events are created THEN the system SHALL store them as append-only entries in S3 storage
3. WHEN the application loads a session THEN the system SHALL replay all events for that session to rebuild the current state
4. WHEN events include DocumentCreated, DocumentEdited, TestRun, ValidationCompleted, DocumentReworked, and other workflow-relevant events THEN the system SHALL handle each event type appropriately during state reconstruction
5. IF event replay fails THEN the system SHALL provide error details and allow partial state recovery from valid events