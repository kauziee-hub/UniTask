# UniTask

Students don't need another dashboard that counts their deadlines. They need to know **what to do next**,
without copying deadlines from Teams by hand.

- **Teams sync.** A student connects their college Microsoft account once. Assignments from their Teams
  classes then flow in automatically, every 30 minutes, through Microsoft Graph. UniTask flags new work,
  moved due dates and removed assignments, and drops anything already turned in on Teams.
- **Do this next.** Everything due (Teams, UniTask classes, personal tasks) is ranked by how much work
  it needs against how much time is left. Each ranking comes with a plain reason: *"Due in 20h · about 3h
  of work · start within 2h"*.
- **Free-time planner.** "I have 2 hours." UniTask fills them with the highest-pressure work and tells you what doesn't fit.
- **Classes like Teams.** Teachers create a class and share a 6-letter code. They post assignments with
  handouts, see who turned in (and who was late), download submissions, grade and return them. Students turn
  in files and notes and get grades back in the same place.

## Run it

Backend (Python 3.11):

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-aws.txt
copy ..\.env.example .env
python scripts\seed_demo.py
uvicorn main:app --reload --port 8000
```

Frontend (Node 20+):

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Demo accounts and a walkthrough are in [docs/DEMO.md](docs/DEMO.md).

## Docs

- [docs/TEAMS_SETUP.md](docs/TEAMS_SETUP.md): register the Microsoft Entra app and connect Teams
- [docs/AWS_PLAN.md](docs/AWS_PLAN.md): which AWS services do what, budget guardrails, and the Claude in Chrome prompt for Console setup
- [docs/DEMO.md](docs/DEMO.md): demo accounts and script
- `docs/MASTER_PROJECT_BRIEF.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/AWS_S3_DEMO_GUIDE.md`: earlier planning documents, kept for history

## Layout

```
backend/
  main.py                 FastAPI app, background Teams sync loop
  app/models.py           users, courses, members, coursework, submissions, changes, connections
  app/teams.py            Microsoft Graph connector: OAuth (MSAL, PKCE), sync and change detection
  app/priority.py         ranking and free-time planning (deterministic, explainable)
  app/security.py         password hashing, sessions, at-rest encryption
  app/cognito.py          Amazon Cognito accounts (AUTH_PROVIDER=cognito)
  app/storage.py          local disk or private S3 with presigned downloads
  app/routers/            auth, courses (teacher), work (student), integrations (Teams)
  scripts/seed_demo.py    demo data through the real API
  tests/                  pytest suite (classroom flow, Teams sync, auth, ranking, storage)
frontend/src/
  pages/student/          Today, Deadlines, assignment detail, Classes, Teams sync
  pages/teacher/          Classes, class page, submissions and grading
```

## Tests

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

```powershell
cd frontend
npm run build
npm run lint
```

## Security notes

- Teams access is read-only and delegated. Refresh tokens are stored encrypted (Fernet, key from `UNITASK_SECRET_KEY`).
- Uploaded files are checked by extension *and* file signature, capped at 15 MB, and stored privately. Downloads use 5-minute links.
- Every API route except sign-in and the Microsoft callback requires a session. Students only see classes they joined and their own Teams items. Only a class's teacher sees its roster and submissions.
- This is still a development setup: run it locally, or put it behind HTTPS before exposing it. Before production, also bind the Teams OAuth `state` to the browser session (a cookie) as well as to the user.
