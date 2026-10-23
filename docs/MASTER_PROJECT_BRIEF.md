Master Project Brief: UniTask AI — Agentic AI-Powered University Assignment Aggregator

1. Project Overview
   I want to build a full-stack, AI-powered academic productivity platform called UniTask AI that helps university students track, organize, understand, prioritize, and complete assignments and academic tasks posted across multiple applications.
   The project is intended to demonstrate practical skills in:
   React frontend development
   Backend development and REST APIs
   Database design and multi-user data management
   Agentic AI and LLM integration
   Tool calling and potentially MCP (Model Context Protocol)
   Third-party application integrations and authentication
   AWS cloud architecture and deployment
   Background jobs, scheduled monitoring, notifications, and security
   The application should solve a real problem experienced by university students: as the number of subjects increases, faculty members may use different applications to publish assignments, quizzes, lab submissions, projects, and other academic work. Students have to visit multiple platforms to identify their pending work and remember different deadlines, making it easy to miss submissions or overlook important tasks.
   UniTask AI should bring this information into one centralized platform and provide an intelligent assistant that can interpret each student's individual requirements and turn them into useful, personalized academic dashboards and plans.
2. Core Problem Statement
   A student might have six or more subjects, with faculty members using different platforms such as Moodle, Google Classroom, Microsoft Teams, university LMS portals, or other assignment management systems.
   For example:
   Compiler Design assignments are posted on Moodle.
   Database Management Systems submissions are posted on a university portal.
   Computer Networks lab work is shared through another application.
   A professor announces a quiz deadline through an integrated learning platform.
   A different subject has a project submission deadline and a grading weightage.
   Students must manually navigate these different platforms, check for newly posted work, record deadlines, and determine which tasks should be completed first.
   This creates information overload, confusion, poor prioritization, and missed deadlines.
   The goal is to provide a single academic workspace where students can see all their pending work across subjects and applications, receive updates when new work is posted, and use natural-language prompts to generate personalized assignment plans and dashboards.
3. User Onboarding and Initial Configuration
   When a student first signs up, the application should guide them through a structured onboarding workflow.
   Step 1: Create an account
   Allow students to register and log in securely.
   Collect relevant profile information such as:
   Name
   College or university
   Degree/program
   Current semester
   Academic department
   Student registration number, if genuinely necessary
   Time zone and notification preferences
   Do not collect sensitive student identifiers unless they are required. Registration numbers should be optional for the initial prototype.
   Each account must have its own isolated data and connected applications.
   Step 2: Configure the semester and subjects
   Ask the student to select or enter their current semester and subjects.
   Where possible, allow subjects to be entered manually, imported from a supported timetable, or selected from a college-specific subject list.
   Each subject should have a unique internal identifier and be associated with the student's account.
   Step 3: Upload the timetable
   Allow the student to upload a timetable image or screenshot, such as a timetable exported from the university portal.
   The application should process the image using OCR, computer vision, or a suitable multimodal AI model to identify:
   Subject names or codes
   Days of the week
   Class timings
   Timetable entries
   Other clearly identifiable scheduling information
   The extracted information must be shown in an editable confirmation screen.
   If the image is unclear, the system must ask the student to correct or confirm the extracted details rather than silently accepting potentially incorrect subjects.
   The timetable should be used to populate or validate the student's subject list. It should not be treated as the source of assignment deadlines, since those deadlines come from assignment platforms.
   Step 4: Map each subject to its assignment platform
   For every subject, ask the student where faculty members publish assignments and related academic work.
   For example:
   Subject Assignment platform
   Compiler Design Moodle
   Database Systems University LMS
   Computer Networks Microsoft Teams
   Financial Analytics Google Classroom
   Allow students to configure:
   Platform name
   Official application URL or course URL
   Subject or course identifier, if available
   Authentication/connection status
   Monitoring frequency
   Whether assignment announcements, quizzes, lab work, projects, or other task types should be tracked
   A single platform may contain several subjects, and a subject may use multiple platforms. The data model must support these cases.
   Important integration requirement: entering a URL does not automatically give the application permission to read the platform. The system must use an official API, OAuth authorization, an approved integration, or another explicitly permitted access method. For unsupported platforms, offer manual entry or an import mechanism rather than claiming automatic access.
   Step 5: Initial synchronization
   After configuration, the application should attempt to retrieve existing assignments from supported integrations.
   Display connection and synchronization status for every subject/platform combination.
   The application should explain which platforms are connected, which require authentication, and which are not yet supported.
4. Centralized Assignment Dashboard
   The dashboard is the main interface of the application.
   Its purpose is to consolidate academic work from every configured subject and supported platform into one understandable view.
   It should include:
   A. Overview
   Display summary cards such as:
   Total pending assignments
   Tasks due today
   Tasks due this week
   Overdue assignments
   Upcoming quizzes and examinations, when supported
   Completed tasks
   Newly discovered assignments
   B. Unified assignment list
   Each assignment should display the information available from its source:
   Assignment title
   Subject
   Original platform
   Assignment description or instructions
   Deadline, including time and time zone where available
   Discovery date or last-updated time
   Estimated effort, if available or explicitly estimated
   Grading weightage, if published
   Status: pending, in progress, completed, overdue, or awaiting clarification
   Original assignment link
   Source synchronization status
   Students should be able to filter, sort, and search assignments by subject, deadline, platform, task type, status, and importance.
   Do not invent missing deadlines, marks, or weightages. Display unknown information as unavailable.
   C. Priority and planning
   The application should identify which tasks need attention first.
   Prioritization should consider:
   Deadline proximity
   Published marks or grading weightage
   Estimated work required
   Whether a task is overdue
   Whether the task blocks or depends on another task
   Student-defined preferences
   Explain why a task has been ranked as important.
   Do not equate an AI-generated priority score with actual academic grading weightage.
   D. Calendar and visualizations
   Provide useful views such as:
   Calendar of upcoming deadlines
   Subject-wise assignment distribution
   Workload by day or week
   Pending versus completed work
   Upcoming high-priority tasks
   Visualizations should be simple and actionable rather than overwhelming the student with charts.
   E. Task interaction
   Allow students to mark assignments as completed, in progress, or pending, add notes, set personal reminders, and optionally estimate the time they need.
   Keep the original platform's assignment status separate from the student's local tracking status when the integration does not support updating the original platform.
5. Natural-Language Agentic AI Assistant — The Core Feature
   The most important differentiating feature is a natural-language interface within the React frontend.
   Students should be able to type a request in their own words, without manually configuring filters or navigating every assignment.
   Example prompts include:
   "I will not be available from 25 October to 28 October. Show me everything I should complete before then."
   "List all pending assignments across my subjects and order them by deadline and importance."
   "Which assignments have the nearest deadlines?"
   "I have only three hours today. Help me decide what to work on."
   "Show me the most important submissions for this week."
   "Do I have any newly posted assignments?"
   "Give me a manageable plan for completing my work before Friday."
   "Show me all assignments worth more than 10 marks."
   "Which subjects have the most pending work?"
   "Summarize the instructions and submission requirements for my next assignment."
   The agent should interpret the user's request, identify the relevant data and actions required, use approved tools, and return a structured response.
   Agent workflow
   The intended workflow is:
   The student submits a prompt through the React interface.
   The frontend sends the authenticated request to the backend.
   The backend identifies the user and loads the necessary context and permissions.
   The agent interprets the intent and determines which tools are required.
   The agent calls appropriate tools, such as searching assignments, retrieving deadlines, filtering by date, ranking tasks, or generating a study plan.
   Tools retrieve data from the application's database or supported external integrations.
   The agent interprets the results and produces a structured, personalized response.
   The backend validates the response and any generated dashboard data.
   The frontend displays the answer using useful UI components, such as assignment cards, grouped lists, deadline timelines, charts, or calendar views.
   The agent should not be forced to answer every request with plain text. When appropriate, it should return structured data that the frontend can render into an interactive dashboard.
   Example interaction
   User prompt:
   "I am unavailable until 28 October. Tell me what I should finish before then, ranked by importance, and give me a simple plan."
   The system should:
   Determine the relevant date range.
   Retrieve the user's pending assignments from all connected subjects.
   Exclude completed tasks.
   Identify tasks due before or during the requested period, while distinguishing any optional early-completion recommendations.
   Consider deadlines, published grading weightage, estimated effort, and overdue status.
   Identify missing or uncertain information.
   Rank the tasks with an explanation.
   Generate a realistic daily plan, taking into account the timetable and the student's available time if known.
   Display the results as assignment cards and a timeline or schedule.
   Provide direct links to the original assignment platforms.
   If necessary information is missing, the assistant should ask a short clarifying question instead of fabricating facts.
6. Agentic Framework, Tools, and MCP
   I am unsure whether this project should use an agentic framework, MCP, direct API integrations, or a combination of these. The architecture recommendation must explain the distinction and choose a practical approach.
   Agentic framework
   Use an agent runtime or framework to manage the LLM interaction loop, tool selection, tool results, and multi-step reasoning where necessary.
   Potential options include LangGraph, a lightweight custom Python agent loop, or another appropriate framework.
   Avoid introducing a large multi-agent architecture unless there is a clear benefit.
   Tools
   Design explicit backend tools, such as:
   get_user_subjects
   get_user_timetable
   list_assignments
   get_assignment_details
   filter_assignments_by_date
   rank_assignments
   generate_study_plan
   get_sync_status
   get_new_assignments
   create_personal_reminder
   update_local_task_status
   Each tool should have a defined input schema, output schema, validation rules, and permission checks.
   Use deterministic code for database queries, date filtering, deadline calculations, and other operations where correctness is more important than free-form model reasoning.
   The LLM should interpret the user's intent and coordinate the tools, not independently invent or calculate critical assignment information without validation.
   MCP
   Model Context Protocol may be used to expose assignment-retrieval and planning capabilities to a compatible agent through standardized tool interfaces.
   For the initial implementation, compare these approaches:
   Direct Python function tools called by the agent
   An MCP server exposing selected tools
   A combination of internal functions and MCP integrations
   Do not assume MCP is required for an agent to function. Choose it if the standardized integration layer provides a meaningful benefit.
   External platform integrations
   Create a connector architecture that supports individual platform adapters.
   Each adapter should implement a common interface for retrieving courses, assignments, deadlines, and source links where the external platform supports those capabilities.
   Examples of potential future integrations include Moodle, Google Classroom, Microsoft Teams, and institution-specific LMS portals.
   Prioritize one integration that can actually be tested. Do not claim every platform supports the same APIs or permissions.
   Where no supported API is available, provide manual assignment entry, CSV/ICS imports, or another authorized fallback.
   The system must not bypass login controls, MFA, access permissions, or platform restrictions.
7. Automated Monitoring and Synchronization
   The application must support regularly checking configured assignment platforms for newly published or modified tasks.
   The intended workflow is:
   A scheduler triggers synchronization for connected platforms.
   The relevant connector retrieves new or updated assignments.
   The backend normalizes the data into a common assignment format.
   The database inserts new assignments or updates existing ones.
   Duplicate detection prevents repeated assignments from appearing after every sync.
   Assignment changes and synchronization errors are recorded.
   The dashboard reflects the latest available information.
   Notifications can be sent for new assignments, changed deadlines, approaching deadlines, or failed connections.
   Synchronization should be incremental where supported.
   The application should respect API rate limits, provider terms, user permissions, and connection expiration. It should also display when the data was last synchronized, because it cannot guarantee instant detection of every new assignment.
   Use background jobs for synchronization rather than making the user wait for every platform to be checked during a dashboard request.
8. Database and Data Model
   Design a multi-user data model that includes, as appropriate:
   Users
   Academic institutions
   Semesters
   Subjects
   Timetable entries
   Connected applications
   Platform/course mappings
   Assignment records
   Assignment source identifiers
   Local assignment status
   Published marks or weightage
   Task estimates and priority information
   Synchronization history
   Notifications and reminders
   Agent task history
   User preferences
   OAuth connection metadata
   Each assignment should retain its original platform identifier and source URL when available, allowing reliable deduplication and traceability.
   Clearly distinguish source data obtained from an LMS from student-created information and AI-generated estimates.
   Recommend an appropriate primary database. PostgreSQL or another relational database is a reasonable starting point because users, subjects, platform mappings, assignments, and deadlines have clear relationships. Explain whether DynamoDB is justified for this project or whether using it would add unnecessary complexity.
   Do not require a separate vector database unless a genuine semantic-search feature is included. Ordinary assignment filtering and deadline queries can be handled using a conventional database.
9. AWS Cloud Architecture Requirements
   This is also a Cloud Architecture and Design project, so AWS must be meaningfully incorporated into the implementation.
   Recommend a practical architecture that is affordable, demonstrable, and suitable for a student project.
   Consider the following services:
   Amazon EC2 or another suitable compute service: Host the backend and, if appropriate, the agent runtime.
   Amazon S3: Store uploaded timetable images and other required files.
   Amazon RDS for PostgreSQL: Store users, subjects, assignments, mappings, deadlines, task status, and application records.
   Amazon SQS: Queue synchronization jobs or other long-running tasks.
   AWS Lambda or a worker service: Process queued tasks, execute scheduled synchronization, or handle document processing when appropriate.
   Amazon EventBridge Scheduler: Trigger periodic synchronization tasks.
   AWS IAM: Restrict service permissions according to least privilege.
   Amazon CloudWatch: Record logs, errors, and operational metrics.
   AWS Secrets Manager or an equivalent secure configuration mechanism: Protect credentials and API secrets.
   These are candidate services, not mandatory services. Recommend the smallest useful set for the initial implementation and explain the purpose of each selected service.
   Avoid using S3 as a substitute for a relational database. Store the actual timetable images in S3 and the associated metadata in the database.
   The LLM can be accessed through an external model API or a suitable managed AI service. Do not require self-hosting an LLM on a GPU unless there is a strong reason.
   The architecture should distinguish between hosting the agent application and hosting the model.
   If AWS deployment would make the project unnecessarily expensive or complex, propose a staged approach: develop locally first, then deploy a working cloud version using a limited set of AWS services.
10. Security and Privacy
    The application must implement security from the beginning.
    Requirements include:
    Secure registration and authentication.
    Authorization on every user-specific API and tool.
    Strict isolation between different students' assignments and connected accounts.
    Safe handling of OAuth access and refresh tokens.
    Encrypted transmission and appropriate encryption at rest.
    Server-side secret management.
    Input validation and output validation.
    Rate limiting and sensible API error handling.
    Safe file-upload validation.
    Audit logs for relevant actions.
    Minimal collection of student information.
    Clear procedures for disconnecting an integration and deleting user data.
    The LLM must not decide its own permissions. Backend policy checks must determine which records and actions a user can access.
    Treat assignment descriptions and external content as untrusted data, since they may contain malicious or irrelevant instructions intended to manipulate the agent.
    The initial agent should primarily be read-only. Any future functionality that submits work, changes a deadline on an external platform, or performs another consequential action must have explicit authorization and, where appropriate, user confirmation.
    Never store raw application passwords as a shortcut for integrations.
11. Frontend Requirements
    Build a clean, modern, responsive React application with an intuitive user experience.
    Required screens:
    Registration and login.
    Onboarding wizard.
    Subject and semester configuration.
    Timetable image upload and extraction confirmation.
    Subject-to-platform mapping.
    Application connection and synchronization status.
    Main assignment dashboard.
    Assignment details.
    Calendar and planning view.
    Natural-language AI assistant.
    User preferences and notification settings.
    The AI interface should be integrated into the dashboard rather than feeling like an unrelated chatbot.
    When a student asks a question, display both the agent's concise explanation and useful visual components.
    For example, a prompt requesting all pending assignments could produce a grouped assignment list, urgency indicators, deadlines, and links to original sources.
    Avoid clutter, excessive charts, unnecessary animations, and unsupported claims. The interface should reduce the student's cognitive load.
12. Backend and API Requirements
    Use a clear separation between:
    Authentication and user management
    Subject and timetable management
    Assignment management
    External platform connectors
    Synchronization workers
    Agent orchestration
    Tool execution
    Planning and prioritization logic
    Notification services
    Database access
    AWS integrations
    A Python backend using FastAPI is a preferred option because it integrates well with Python-based agent frameworks and asynchronous APIs, although another suitable stack may be justified.
    Provide well-defined REST API endpoints for the React frontend.
    Use structured request/response schemas, correct HTTP status codes, centralized error handling, pagination where necessary, and server-side authorization.
    Long-running tasks should return a task identifier and status rather than keeping the HTTP request open indefinitely.
13. Functional Requirements and Development Phases
    Implement the project incrementally.
    Phase 1: Working full-stack foundation
    Registration and login.
    Subject and semester setup.
    Manual assignment entry.
    Assignment CRUD operations.
    Unified dashboard.
    Sorting, filtering, and deadline tracking.
    Database integration.
    Phase 2: Timetable processing
    Timetable image upload.
    OCR or AI-assisted subject extraction.
    Editable confirmation screen.
    Timetable persistence.
    Phase 3: Agentic AI
    LLM integration.
    Natural-language assignment queries.
    Tool calling.
    Deterministic deadline filtering and priority calculation.
    Personalized study-plan generation.
    Structured output rendered as dashboard components.
    Phase 4: External integrations
    Implement one supported LMS connector.
    Connect using its documented authentication method.
    Retrieve existing assignments.
    Normalize and deduplicate assignment records.
    Display synchronization status.
    Add manual entry/import fallbacks.
    Phase 5: Scheduled automation
    Background job queue.
    Periodic synchronization.
    New-assignment detection.
    Deadline-change detection.
    Notifications and retry handling.
    Phase 6: AWS deployment
    Deploy the backend and frontend.
    Configure the database and file storage.
    Add the necessary queue and scheduler if selected.
    Configure IAM, secrets, logging, and monitoring.
    Demonstrate the cloud architecture working end to end.
    Phase 7: Testing and refinement
    Unit tests for deadline and priority logic.
    API integration tests.
    Authentication and authorization tests.
    Tests for duplicate assignments.
    Tests for expired connections and failed synchronizations.
    Agent tool-selection and output-validation tests.
    Tests for attempts to access another user's records.
    Performance and error-handling checks.
14. Important Architectural Decisions to Make
    Before implementation, analyze and recommend:
    The most appropriate agent framework, or whether a lightweight custom agent loop is enough.
    Whether MCP is necessary for the first version.
    Which single LMS integration is the most practical to demonstrate.
    The best primary database and whether a separate vector database is unnecessary.
    Which AWS services provide real value without unnecessary complexity.
    How to implement reliable periodic synchronization.
    How to prevent duplicate records and handle changed deadlines.
    How to securely store each student's application connections.
    How to isolate users' data and enforce permissions.
    How to generate structured agent outputs for a dynamic React dashboard.
    How to keep LLM costs manageable.
    How to deploy and demonstrate the project within a student budget.
    Make realistic assumptions and explain trade-offs instead of using every available technology.
15. What I Want From You
    Using this entire project brief, generate a comprehensive master implementation prompt for an AI coding tool that can help build the application.
    The master prompt must:
    Preserve the complete core idea described above.
    Define the product requirements and intended user experience.
    Specify the recommended technology stack.
    Describe the system architecture and data flow.
    Define the database schema and relationships.
    Define the frontend pages and reusable components.
    Define backend modules and API contracts.
    Explain the agent loop, available tools, and MCP decision.
    Explain external application authentication and connector design.
    Explain the synchronization pipeline and background jobs.
    Specify AWS services and explain how they fit together.
    Define security, authorization, and privacy requirements.
    Include an implementation plan with explicit milestones.
    Include acceptance criteria and test cases.
    Include environment-variable and deployment requirements.
    Include a sensible project directory structure.
    Include local development and AWS deployment instructions.
    Make the implementation beginner-friendly, with explanations of why major components are needed.
    The resulting master prompt should instruct the coding AI to build a functional application incrementally, verify each milestone, and avoid generating a huge untested codebase in a single step.
    The application must be designed so that the first version is genuinely usable even if only one external LMS integration is available. Other platforms should be added through the connector architecture later.
    Prioritize a working end-to-end product, correctness of assignment data, a polished UI, safe agent tool execution, and a demonstrable AWS deployment over unnecessary complexity or fashionable technology choices
