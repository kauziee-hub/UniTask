# UniTask AI — Architecture Decisions

This document records the current repository audit and the proposed implementation architecture. The product requirements remain in [MASTER_PROJECT_BRIEF.md](./MASTER_PROJECT_BRIEF.md), which is the source of truth.

## Repository audit (2026-10-23)

| Area | Observed state | Decision |
| --- | --- | --- |
| Repository | The workspace root is not currently a Git repository; there is no root-level Git configuration. | Keep source changes local; initialize/version the project when the owner is ready. |
| Frontend | `frontend/` is a Vite + React + TypeScript app. React 19, React Router 7, Lucide React and ESLint are already declared; dependencies are installed. Existing UI was the Vite starter. | Preserve Vite and the existing frontend environment; no package installation is needed for Milestone 1. |
| Backend | `backend/requirements.txt` and a Python 3.11 `.venv` exist. No application source, configuration, migration setup, or backend tests are present outside the environment. | Build FastAPI foundations in a later milestone; do not generate backend scaffolding during the frontend-only milestone. |
| Product brief | `docs/MASTER_PROJECT_BRIEF.md` exists and specifies the product and requirements. | Treat as read-only and authoritative. |
| Other documentation | Architecture and progress documents existed but were empty. There was no root README. | Populate both requested docs and add a short root README with local frontend instructions. |
| Infrastructure/scripts | `infrastructure/` and `scripts/` exist but contain no implementation files. | Do not provision or add infrastructure before local application functionality is established. |
| Local services | No root Docker Compose file, PostgreSQL configuration, or frontend/backend integration is present. | Add PostgreSQL and Docker Compose with the backend foundation in Milestone 2. |
| Configuration | No application `.env.example` is currently required by the static frontend. | Introduce it alongside backend/database configuration, with placeholders only. |

## Recommended project structure

```text
docs/
  MASTER_PROJECT_BRIEF.md
  ARCHITECTURE_DECISIONS.md
  IMPLEMENTATION_PROGRESS.md
frontend/
  src/
    components/       # shared shell and reusable UI
    data/             # prototype-only sample records
    pages/            # route-level screens
    services/         # typed API clients, added with backend integration
    types/             # shared frontend contracts, as needed
backend/
  app/
    api/               # FastAPI routers and dependencies
    core/              # settings, auth helpers, error handling
    models/             # SQLAlchemy entities
    schemas/            # Pydantic request/response contracts
    services/           # business operations and authorization
    connectors/         # authorized LMS adapters
    agent/              # orchestration and explicit tools
    workers/            # idempotent background jobs
  alembic/              # database migrations
  tests/
infrastructure/         # deployment templates/configuration when approved
```

Keep services thin and introduce repository abstractions only where repeated query logic warrants them. Frontend sample records must not become the future API layer; API clients and UI-facing contracts should be introduced separately.

## Frontend architecture

- React + TypeScript + Vite remains the client stack. React Router provides URL-based navigation.
- Route-level pages compose shared components; the responsive application shell owns sidebar/top navigation and theme controls.
- Design tokens are CSS custom properties in `frontend/src/index.css`; shared layout and component rules live in `frontend/src/App.css`.
- Prototype records and their types live in `frontend/src/data/sampleData.ts`. This is explicitly mock data, separate from later API services.
- Login and registration are presentation-only in Milestone 1. They must not imply account creation or authorization before a backend is implemented.
- Loading, empty, and error feedback share a reusable component. Empty results and not-found errors are rendered now; an active loading screen is intentionally not simulated while the app has no asynchronous data requests.

## Backend architecture

Use FastAPI with a modular monolith as the first deployable shape:

1. Routers parse HTTP requests and bind authenticated-user dependencies.
2. Pydantic schemas validate input and shape responses.
3. Services implement deterministic business behavior and enforce ownership.
4. SQLAlchemy models and Alembic migrations persist relational data in PostgreSQL.
5. Connectors, agent tools, and workers call authorized services; they do not access arbitrary user data directly.

This keeps deployment and debugging manageable for a student project while preserving module boundaries. Separate deployable services are not justified yet.

## Proposed data model

The exact schema should be refined against each milestone's acceptance criteria. The initial relational model is:

- `users` — credentials and minimum account metadata; password hashes only.
- `user_profiles` and `user_preferences` — optional academic details, time zone, theme and notification settings.
- `semesters` — owner, label, start/end dates, and active state.
- `subjects` — owner and semester foreign keys, course code, name and display color.
- `timetable_entries` — owner/subject, weekday, start/end time and source/confirmation metadata; uploaded image metadata points to object storage, not a database blob.
- `platforms` — supported provider identities and integration capability metadata.
- `lms_connections` — owner, provider, OAuth metadata/status and encrypted token references; never raw LMS passwords.
- `subject_platform_mappings` — many-to-many subject/course/provider mapping, course IDs and enabled task types.
- `assignments` — owner/subject, normalized title/details, due time/time zone, source, source ID/URL, original platform status, local tracking status, published grade weight, and provenance for estimates.
- `assignment_status_history` — local status changes and timestamps.
- `sync_jobs` and `sync_logs` — idempotency key, state, retry count, provider timestamps and diagnostic outcome.
- `reminders` and `notifications` — owner, assignment or schedule relation, delivery state, preferences and timestamps.
- `study_plans` — user-requested plan metadata and validated structured items.

Use foreign keys and unique `(connection_id, source_assignment_id)` constraints for deduplication; index owner/subject/due-time/status paths. Keep source values distinct from student input and model-generated estimates. Apply consistent deletion rules and test tenant isolation. PostgreSQL is the single initial database: relational joins, constraints, and deadline filters fit the domain. A vector store is not justified without a real semantic-search requirement; DynamoDB would duplicate capability and add operational cost.

## API plan (later milestones)

Use `/api/v1` and standard JSON responses. Authenticated user identity comes from the server-side credential, never from a client-supplied owner ID.

| Method and path | Purpose |
| --- | --- |
| `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` | Account/session lifecycle |
| `GET/PATCH /users/me` | Current user's profile and preferences |
| `GET/POST /semesters`, `GET/PATCH/DELETE /semesters/{id}` | Semester configuration |
| `GET/POST /subjects`, `GET/PATCH/DELETE /subjects/{id}` | User's subjects |
| `GET/POST /timetable-entries`, `POST /timetables/uploads`, `POST /timetables/{id}/confirm` | Timetable upload, review and confirmed entries |
| `GET/POST /assignments`, `GET/PATCH/DELETE /assignments/{id}` | Assignment CRUD with filtering, sorting and pagination |
| `GET /dashboard/summary`, `GET /calendar` | Aggregated view and deadline range |
| `POST /reminders`, `GET/PATCH/DELETE /reminders/{id}` | Personal reminders |
| `GET/POST /connections`, `DELETE /connections/{id}`, `GET /connections/{id}/sync-status` | Authorized integration lifecycle |
| `POST /sync-jobs`, `GET /sync-jobs/{id}` | Queue/sync status without holding long HTTP requests |
| `POST /agent/messages` | Authenticated assistant request with validated structured response |

Apply owner checks in services for every user-specific resource; return not-found for inaccessible IDs where that avoids confirming another user's resource. Define error models and OpenAPI contracts before frontend API wiring.

## Agent runtime and tools

Start with a small custom Python tool loop once actual assignment services exist. It is easier to understand and test than a multi-agent graph for the first read-mostly use cases. Re-evaluate LangGraph if stateful branching, durable multi-step workflows, or observability needs outgrow the simple loop. Expose allow-listed typed functions such as `list_assignments`, `get_assignment_details`, `filter_assignments_by_date`, `rank_assignments`, `generate_study_plan`, and `get_sync_status`; bind the authenticated user context server-side and pass only necessary fields to the model. Deterministic date filters, calculations, authorization and validation remain Python responsibilities. Bound iterations/tool calls, validate tool schemas and final output, and return explicit provider errors.

MCP is not required initially: internal Python calls are simpler and avoid another service/protocol boundary. Reconsider MCP only if the same approved tools need to be shared with independent compatible clients. The LLM is an external service called by the backend; it is not hosted in the frontend. Treat source assignment text as untrusted data/instructions.

## LMS connectors and synchronization

Define an adapter contract for provider capability, OAuth flow (where supported), course discovery, assignment retrieval, normalization, pagination/rate limits and error reporting. Select one real integration only after confirming an authorized API, test tenant/account, and credentials. Use manual entry/import where not supported; never automate login or evade controls.

Sync should run asynchronously after an authenticated request or schedule: enqueue a job, fetch incremental source data, normalize, upsert by connection/provider source ID, record deadline changes and errors, then expose last-success/last-attempt status. Jobs need idempotency keys, bounded retries, backoff and rate-limit handling. Keep source status separate from the student's local task status.

## Background processing

First local backend milestone: implement an in-process or CLI-triggered worker only if needed for the demonstrable feature. For deployment, use SQS plus a small worker or Lambda for bounded event jobs; EventBridge Scheduler can enqueue periodic sync tasks. Store job state in PostgreSQL and make handlers idempotent. Avoid running scheduled sync in web request handlers.

## AWS deployment recommendation (not provisioned)

Develop locally first. For a demonstrable cloud stage, use:

- **EC2** for a modest backend/worker deployment if a single host is the simplest student-budget option; keep frontend static hosting separately.
- **RDS PostgreSQL** for managed relational data.
- **S3** for validated timetable images, with private buckets and short-lived presigned access.
- **Secrets Manager** (or carefully managed deployment secrets) for production credentials.
- **CloudWatch** for application logs and operational alarms.
- **SQS + EventBridge Scheduler** only when scheduled, retryable sync is implemented.
- **IAM** least-privilege roles for access to specific buckets/queues/secrets.
- **Lambda** only for short event-driven processing where it reduces maintenance; do not add it alongside a worker without a specific need.

No AWS resource is to be created without explicit approval. Keep local development independent of AWS credentials. Estimate costs and define teardown steps before deployment.

## Security and privacy

- Use a maintained password hashing implementation (Argon2id or bcrypt), secure session/token handling, HTTPS in deployment and rate limits on auth endpoints.
- Authenticate at the API boundary and enforce resource ownership in service methods, including agent tools and background operations.
- Collect only needed academic/profile fields. Avoid mandatory student registration numbers.
- Validate upload size, media type and decoded image format; store private files outside the web root.
- Keep secrets out of source control; production tokens are encrypted and access-controlled, never raw provider passwords.
- Validate external and LLM data against schemas. Do not accept model-generated user IDs or permissions.
- Add audit records for authentication, connection changes, important local status changes, and user-data deletion.
- Provide connection revocation and account/data deletion workflows before production use.

## Development milestones

1. **Frontend foundation** — design tokens, responsive shell, routes, presentation-only auth, and browser-local demo workflows (complete; backend/auth still absent).
2. **Backend foundation** — FastAPI config, health endpoint, PostgreSQL Compose service, SQLAlchemy/Alembic structure and tests.
3. **Authentication and users** — secure registration/login, profile, server-derived identity and tenant isolation.
4. **Academic configuration** — semesters, subjects and user preferences.
5. **Timetable workflow** — validated upload, extraction draft, editable confirmation and persistence.
6. **Assignments and dashboard integration** — CRUD, filtering, status tracking and real summary API.
7. **Calendar, reminders and planning** — deadline views and local reminders.
8. **Agent tools and orchestration** — read-only tools, structured output, bounded calls and tests.
9. **Assistant UI integration** — verified data cards and transparent generated suggestions.
10. **One authorized LMS connector** — provider mapping, OAuth/API access, normalization and dedupe.
11. **Background sync and notifications** — queued jobs, retries, schedule and delivery preferences.
12. **Security and comprehensive testing** — threat-focused authorization, file and agent tests.
13. **AWS deployment** — only with explicit approval; deploy the working local system with minimal services.
14. **Production verification** — monitoring, cost/operations review and final documentation.

Do not begin the next major milestone without explicit approval.

## Testing strategy

- Frontend: production build/type-check, ESLint, route/navigation/theme/responsive smoke tests and component behavior tests when a test runner is introduced.
- Backend: unit tests for deterministic date/priority logic; API integration tests against PostgreSQL; migrations tested from empty DB.
- Security: cross-user resource access and tool access denied; invalid/oversized uploads rejected; no secrets returned in errors/logs.
- Integrations: normalization, duplicate upsert, deadline-change, expired-token, rate-limit and failure/retry cases using mocks plus authorized provider test credentials.
- Agent: tool input/output validation, bounded calls, prompt-injection content treated as data, deterministic results, and no data leakage.
- Deployment: health/readiness, DB connection, private file access, worker retry and monitoring checks.

## Zero-cost AWS and timetable upload update (2026-10-23)

- The inspected host does not have the AWS CLI installed. Therefore `aws sts get-caller-identity --profile unitask-demo`, profile inspection, S3 listing, account-plan verification, and account-specific Free Tier verification could not be performed.
- The account plan, S3 free allowance, offer duration/limits, current usage, and charge/tax exposure remain **unknown**. No AWS resources were created, and no real S3 upload was attempted.
- Timetable uploads now use a configurable local/S3 storage adapter. Local private file storage is the default; S3 code is optional and requires an already-approved private bucket.
- Because the project has no authentication, timetable and other API records are not isolated by user. Keep the API local and do not expose it publicly until authentication/authorization is implemented.