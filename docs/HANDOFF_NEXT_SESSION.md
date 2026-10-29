# Handoff: continue the UniTask AI 3.0 build

Paste this file, together with the original "UNITASK AI 3.0 MASTER PRODUCT TRANSFORMATION" prompt, into the next Claude Code session.

## Rules the user set (must follow)

- **NEVER push to GitHub.** No commits unless the user explicitly asks. No `git reset --hard` or `git clean`.
- Branch `teams-classroom`. All work is uncommitted.
- The student experience is the core product. Teacher and classroom features must stay but must not dominate.
- The user supplied a Gemini key and wants it used. It is in `backend/.env` (gitignored) as `GEMINI_API_KEY`. Do not put it in the frontend, docs or build artifacts, and do not nag about rotating it.
- The user wants **novel, deeply personalised features**, especially an AI tutor that teaches *this* student at their own pace and level of understanding.
- The user also wants the analytics and everything else from the original repo back, built better.

## Backup

A snapshot taken before this phase is at `C:\Users\KausikGH\Documents\Projects\UniTask-backups\snapshot-20261029-123902.zip`. It contains the source, a diff against `main`, and local data, but no `.env`.

## State at handoff (verified)

- `backend` tests: **20 passed** (`cd backend; .venv\Scripts\python.exe -m pytest -q`).
- Frontend: built and linted cleanly at the end of the previous phase. Not rebuilt since, because no frontend changes have been made in this phase.
- Gemini works through the AI Studio endpoint `generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` with header `x-goog-api-key`.
  - `gemini-3.5-flash`: about 6 s. Configured as `LLM_MODEL`.
  - `gemini-flash-lite-latest`: about 2.5 s. Configured as `LLM_FAST_MODEL`.
  - `gemini-2.5-flash` is retired for new users, and `gemini-flash-latest` timed out.
  - Vertex AI endpoints return 403. Don't use them.

## Done in this phase (backend only; files are written and they import)

| File | What it is | Tested? |
| --- | --- | --- |
| `backend/alembic.ini`, `backend/migrations/` | Alembic. `0001_classroom_baseline` covers the 9 classroom tables. `0002_academic_workspace` adds 23 tables plus new columns. | Manually: upgrade from empty → 0002, downgrade → 0001, re-upgrade all work. **No pytest yet.** |
| `backend/app/migrate.py` | `upgrade_database(engine)`. Stamps old `create_all` DBs at 0001; handles the original-repo DB (renames `timetable_uploads`, keeps the legacy `subjects`/`assignments` tables). | Manually, empty DB only |
| `backend/app/academic_models.py` | New tables: Profile (learner model), CourseworkSource, Subtask, Topic, TopicLink, Exam (+`exam_topics`), Material, MaterialPage, MaterialTopic, Question (PYQ), PlanBlock, StudySession, TimetableEntry, AttendanceMark, RevisionCard, Attempt, InboxEvent, SyncRun, Conversation, Message, TutorMemory, AuditEvent. Imported at the end of `models.py`. | Imports only |
| `backend/app/models.py` | Added `Coursework.kind`, `Coursework.due_confidence`; `Submission.notes`, `.local_done_at`, `.source_status`, `.snoozed_until`, `.snooze_reason`; `Connection.config`; `TimetableUpload.owner_id`. | Imports only |
| `backend/app/llm.py` | `generate(system, turns, json_mode, fast, image)` for Gemini/Bedrock/none, with a bounded retry and fallback model. `available()`, `describe()`. | Endpoint probed manually; no unit tests |
| `backend/app/extraction.py` | PDF (pypdf), DOCX, PPTX, text → per-page text; OCR via Textract (`OCR_PROVIDER=textract`) or the vision LLM. | No |
| `backend/app/retrieval.py` | BM25 keyword search over MaterialPage, with excerpts and `Hit.cite()`. | No |
| `backend/app/academic.py` | `notify()` (idempotent inbox via dedupe_key), `audit()`, syllabus parse (rules → LLM fallback), `save_syllabus`, topic↔page linking, PYQ parsing + `pattern_key` repetition clustering, `process_material()` pipeline. | No |
| `backend/app/ingest.py` | `SourceEvent` adapter contract + `ingest()`: idempotent upsert, cross-platform dedupe (title + due ±12h), change history, inbox events, full-snapshot removal, SyncRun. | No |
| `backend/app/ics.py` | iCalendar parse (Moodle feeds and imports) and export. | No |
| `backend/app/scheduler.py` | Pure deterministic planner: `weekly_busy`, `conflicts`, `free_slots`, `schedule` (EDF, 25–90 min chunks, daily cap, never after the deadline, unfit + risk + load per day). | No |
| `backend/app/rescue.py` | Exam Rescue selection: value = PYQ frequency + dependants + coverage gap + weak; greedy within budget; prerequisites first; modes tomorrow/three_day/week/zero/weak/pyq. | No |
| `backend/app/revision.py` | SM-2-lite `review()`, `weakness()`, `evidence_status()`. | No |
| `backend/app/tutor.py` | **Personalised tutor.** Builds a learner brief from Profile (pace/style/background), topic evidence, TutorMemory (misconceptions etc.) and cited excerpts [S1..]. Strips invented citations. `grade_check()` records an Attempt, and a wrong answer becomes a revision card plus a misconception memory. Falls back to raw excerpts when the LLM is down. | No |
| `backend/app/jobs.py`, `job_handlers.py`, `worker.py` | Job queue (`JOB_QUEUE` = local/inline/sqs); handlers `process_material`, `reminders` (inbox + SES email when `EMAIL_PROVIDER=ses`), `sync_all` (Teams + Moodle ICS feeds); SQS worker. | No |
| `backend/app/teams.py` | Now emits inbox events for new / moved / removed items, marks `due_confidence="verified"`, sets `submission.source_status`. | Existing tests pass |
| `backend/app/schemas.py`, `services.py` | `WorkItem` gained kind, due_confidence, last_verified_at, source_status, local_done_at, snoozed_until, snooze_reason, notes, providers. | Existing tests pass |
| `backend/.env` | Added `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, `LLM_MODEL`, `LLM_FAST_MODEL`. | — |
| `backend` deps | `pypdf==6.21.4` is installed in the venv but **not yet pinned in requirements.txt**. | — |

## Incomplete patch (redo first)

`%TEMP%\patch_items.py` failed on its `storage.py` step, so these changes were **not applied**:

1. `storage.validate_document(filename, content, max_bytes=MAX_FILE_BYTES)`: add the `max_bytes` parameter, and add `.webp` (`b"RIFF"`), `.ics` (text), `.json` (text) to `DOCUMENT_TYPES`.
2. `services.store_upload(upload, prefix, max_bytes=..., *, return_content=False)`: pass `max_bytes` through, and return the content when asked.
3. `services.download_link(..., inline=False)`: put `inline` in the token and use `content_disposition_type="inline"` in `serve_local_file`. For S3, pass `download_name=None` when inline so PDFs preview in the browser.

## Next steps, in order

1. Redo the patch above. Pin `pypdf==6.21.4` in `requirements.txt`. Remove the stray `date` import and `__all__` from `ics.py`.
2. `main.py`: replace `Base.metadata.create_all` with `app.migrate.upgrade_database(engine)`. Call `jobs.register_all()`. Run the `reminders` job every ~30 min in the existing loop alongside `sync_all`. Add `POST /internal/cron/{job}` guarded by the `CRON_SECRET` header, for EventBridge Scheduler → Lambda.
3. Add the routers (the planned endpoint list is below), with ownership checks on every query (`user_id == current user`; courses via `services.get_course_for`).
4. Tests: migrations (up, down, stamp of a create_all DB, legacy DB), ingest dedupe and changes, ICS parse, scheduler edge cases (shared deadline, exam overlapping a deadline, exam tomorrow with too little time, unknown effort, conflicts, missed block replan), rescue, revision, PDF extraction + citation accuracy (make a PDF with pypdf/reportlab-free bytes, or a .txt material), tutor with `llm.generate` monkeypatched (invented citations stripped), notify idempotency, cross-user denial for materials/topics/sessions, S3 stubbed put, LLM failure fallback.
5. Frontend (React/Vite, design tokens in `frontend/src/index.css`, existing components `Shell`, `WorkRow`, `ui.tsx`, `lib/api.ts`, `lib/useLoad.ts`). Student nav: Today (command centre), Inbox, Deadlines, Planner+Calendar, Subjects (syllabus map, PYQ), Library (upload/search/ask with citations, PDF preview `#page=N`), Exams (rescue with a time-budget bar + schedule), Study Desk (`/study/:id`: timer, checklist, material panel, tutor, scratch, flashcards, resume), Revision, Tutor (plus a "What the tutor knows about me" memory view with delete), Insights (real charts from sessions/attempts/completions; SVG), Classes, Connections (Teams, Moodle ICS feed, file import, VTOP extension token), Settings (profile, availability, learner style/pace, attendance rule, theme, import data from the old version's browser localStorage key `unitask-demo-data-v1`). The teacher area stays as it is. Onboarding: empty workspace / connect / timetable / syllabus / calendar import / labelled demo.
6. `extension/vtop/`: MV3 extension that reads assignment tables while the student browses VTOP and posts to `/api/extension/ingest` with the student's token. Mark it **unverified against live VTOP**.
7. Deployment: `backend/Dockerfile`, a frontend `VITE_API_BASE` env var (currently relative `/api`), the zip of `frontend/dist` *contents*, a backend artifact, and `docs/deploy/` (DEPLOY_HANDOFF, REQUIRED_AWS_RESOURCES, ENVIRONMENT_CONTRACT, DEPLOYMENT_RUNBOOK, ACCEPTANCE_CHECKLIST, COST_AND_SECURITY_NOTES, RELEASE_MANIFEST.json). Never include `.env`, the DB, or tokens.
8. Browser-test journeys A, B, C and the teacher journey. Update `docs/IMPLEMENTATION_PROGRESS.md` and the feature-preservation matrix truthfully.

## Planned endpoints (not yet written)

- **profile:** GET/PATCH `/api/profile`; GET `/api/ai/status`.
- **subjects:** GET/POST `/api/subjects`; PATCH/DELETE `/api/subjects/{id}` (personal only); GET `/api/subjects/{id}/syllabus`; POST `/api/subjects/{id}/topics`; PATCH/DELETE `/api/topics/{id}`; POST `/api/subjects/{id}/syllabus/extract` {material_id | text}; POST `/api/subjects/{id}/syllabus/confirm`; topic links CRUD + `suggest-links` (suggested=True until accepted); GET `/api/topics/{id}`; GET `/api/subjects/{id}/pyq` (groups by pattern_key, with years and counts, labelled "history, not prediction").
- **materials:** POST `/api/materials` (multipart, sha256 dedupe → 409 with the existing id, enqueue `process_material`); GET list/detail; DELETE; `reprocess`; GET `/{id}/file?inline=1`; GET `/{id}/pages/{n}`; GET `/api/search?q=&course_id=`; POST `/api/ask` (tutor mode "ask").
- **exams:** CRUD; PUT topics; POST `/{id}/rescue` (preview, using `scheduler.free_slots` for the budget unless hours are given); POST `/{id}/rescue/apply` (PlanBlocks with plan=`rescue:{id}`).
- **planner:** GET `/api/planner`; POST `/api/planner/replan` {scope: day|week} (mark past planned blocks missed, rebuild demands from coursework + exams + due cards, persist, return unfit/risk/load/conflicts); PATCH `/api/planner/blocks/{id}`. Note: `/api/plan?minutes=` already exists for the free-time planner.
- **sessions:** POST (resumes an active/paused session for the same target); GET; pause/resume/complete/abandon; PATCH scratch/checklist/resume; list active+paused.
- **revision:** GET `/api/revision` (due, weak topics with reasons, history); cards CRUD; POST `/cards/{id}/review` {grade, confidence}; POST `/topics/{id}/cards/generate` (grounded, with material/page); practice answer grading.
- **tutor:** conversations CRUD; POST `/messages`; POST `/messages/{id}/check`; GET/DELETE `/api/tutor/memory`.
- **inbox:** list, read, dismiss, read-all.
- **calendar:** timetable CRUD, confirm-all, POST `/api/timetable/extract` (image → vision → unconfirmed entries); GET `/api/calendar?start&end` (unified + conflicts); GET `/api/calendar/export.ics`; attendance GET/POST (real records only + the student's own stated threshold).
- **imports:** file (csv/json/ics), Moodle feed URL (encrypted in `Connection.config`, provider `moodle_ics`), POST `/api/capture` {text} (LLM → inferred item that needs confirming), POST `/api/work/{id}/confirm-due`, legacy localStorage import, legacy-DB claim, extension token + ingest.
- **home:** GET `/api/home` (next best action, radar, inbox, today's schedule, study queue, honest progress, missing-material warnings); snooze; breakdown (LLM subtasks, with a deterministic fallback); subtasks CRUD; notes; local-done (kept separate from Teams' status); related materials.
- **insights:** GET `/api/insights` (study minutes per day, completions, on-time rate, coverage per subject, workload over the next 14 days, revision accuracy per topic).

## Run locally

```powershell
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn main:app --reload --port 8000
cd frontend; npm run dev
```

Demo data: `python scripts\seed_demo.py`. Accounts are listed in `docs/DEMO.md`. `.claude/launch.json` has `backend` and `frontend` preview configs.
