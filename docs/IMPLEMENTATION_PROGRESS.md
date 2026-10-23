# UniTask AI — Implementation Progress

## Project audit

Completed 2026-10-23. See [ARCHITECTURE_DECISIONS.md](./ARCHITECTURE_DECISIONS.md) for the audit, planned structure, data model, API, security and infrastructure decisions.

- The existing frontend is Vite + React + TypeScript with React Router, Lucide React and ESLint already installed.
- The prior frontend was the default Vite starter.
- A Python 3.11 virtual environment and pinned `backend/requirements.txt` exist, but the backend has no application source or tests yet.
- The authoritative product brief is present and was left unchanged.
- There is no root Git repository, Docker Compose setup, database configuration, backend `.env.example`, or root README at audit time. A root README is now added; backend/configuration work remains deferred to later milestones.
- No AWS resources have been provisioned.

## Milestones

| # | Milestone | Status |
| --- | --- | --- |
| 1 | Frontend foundation and initial application experience | Complete |
| 2 | FastAPI backend foundation and PostgreSQL | Deferred |
| 3 | Authentication and user management | Not started |
| 4 | Subjects, semesters and academic configuration | Not started |
| 5 | Timetable upload, OCR and confirmation | Not started |
| 6 | Assignment management and dashboard API integration | Not started |
| 7 | Calendar, reminders and study planning | Not started |
| 8 | AI agent architecture and backend tools | Not started |
| 9 | AI assistant frontend integration | Not started |
| 10 | LMS connector architecture and first authorized integration | Not started |
| 11 | Background synchronization and notifications | Not started |
| 12 | Security hardening and comprehensive testing | Not started |
| 13 | AWS deployment and infrastructure integration | Not started |
| 14 | Production verification, monitoring and documentation | Not started |

## Milestone 1 scope and verification

Completed in this milestone:

- Central CSS design tokens, Inter typography, light/dark theme foundation, responsive layout and reusable cards.
- Responsive app shell with route navigation, collapsible sidebar/mobile drawer, theme toggle, dashboard, assignment list, calendar and subject views.
- Separate sample assignment/subject data and a visible sample-data notice; integration pages explicitly do not claim live connections.
- Login and registration layouts that explicitly state authentication is not connected and do not create or authenticate accounts.
- Reusable loading/empty/error feedback component; empty search and route-not-found states are rendered. Loading is not simulated without a real asynchronous operation.
- Global assignment search routes to matching sample assignments; dashboard filter tabs and local search work.
- Root README and architecture/progress documentation.
- Frontend production build, lint, TypeScript validation, and local browser smoke check.

No backend, AI agent, LMS sync or cloud deployment is included.

## Known limitations

- Seed assignments and subjects are initial sample data; edits persist in browser localStorage.
- The login/registration forms are visual only and create no account.
- Integrations are not connected to an API; timetable images are preview-only, without OCR.
- The assistant is deterministic, not an LLM, and only has access to browser-local data.
- Data is device/browser-specific and can be cleared with browser storage or the Reset demo data control.
- No backend, PostgreSQL service, or external LMS connection is implemented.
- Theme choice is currently in-memory for the browser session.

## Testing status

- Frontend build: passed (`npm run build`)
- ESLint: passed (`npm run lint`)
- TypeScript: passed as part of `npm run build` (`tsc -b`)
- Local browser smoke check: passed — dashboard counts update from shared records; assignment add/edit/complete/delete; subject add/edit and persistence on reload; calendar displays saved deadlines; CSV import persists an assignment; deterministic assistant ranks saved work; mobile navigation and existing routes render. No browser page errors observed.

## Demo-readiness update (2026-10-23)

- Add, edit, delete, complete/reopen assignments and create/edit/delete subjects.
- One browser-local shared store persists assignments and subjects in localStorage; dashboard statistics, workload, sidebar count, assignment list and the current-week calendar derive from that store.
- CSV/JSON assignment import maps course codes to existing subjects. Timetable images can be previewed locally; OCR/extraction is not implemented.
- The assistant provides deterministic deadline queries, ranking and simple study suggestions using only local assignments. No LLM provider/backend is configured.
- Sign-in/register are presentation-only. Integrations explicitly show disconnected; no real external LMS platform is accessed.
- The app is prepared for a local demonstration. Backend, OCR, LLM, live LMS and AWS work remains future enhancement.

### Demonstration verification

- `npm run build` — passed, including the TypeScript build.
- `npm run lint` — passed.
- Browser checks rendered every existing route plus `/timetable` and `/register`.
- Assignment create/edit/complete/reopen/delete, subject create/edit, and refresh persistence were exercised.
- Dashboard active-task count changed after completing an item; the current-week calendar uses saved assignment due dates.
- CSV import added a task; the assistant generated a deterministic deadline-ranked study suggestion.
- No browser JavaScript errors were observed.

## AWS zero-cost inspection and upload adapter (2026-10-23)

- Inspection found a local FastAPI backend with SQLite default, assignment/subject routes, and a deterministic assistant; those endpoints are not connected to the frontend's assignment/subject demo data. No authentication/user isolation is present.
- The timetable screen previously only previewed images. It now uploads JPEG/PNG/WebP images (5 MB maximum) to a local backend provider by default; backend validation checks extension, declared MIME type and file signature. File metadata is stored in the database. Retrieval is local or short-lived presigned S3 URL.
- Boto3 is documented in optional `backend/requirements-aws.txt`; normal local operation defaults to filesystem storage.
- AWS CLI is absent. Account identity, plan, S3 Free Tier applicability, limits, expiry, prices and taxes could not be checked. No AWS resource was created; S3 is unconfigured and untested against AWS.
- Frontend Vite proxy forwards `/api` to local FastAPI; no API credentials are exposed to React.