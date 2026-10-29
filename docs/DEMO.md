# Running the demo

For the AWS demonstration, use [the current release handoff](deploy/DEMO_READY.md). Set `DEMO_MODE=true` to seed the synthetic workspaces at startup and show **Open student demo** / **Open teacher demo**, without signup or a password. Leave it off for ordinary account-based deployments.

## Start everything

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-aws.txt
python scripts\seed_demo.py          # demo classes, students, assignments (safe to re-run)
uvicorn main:app --reload --port 8000
```

```powershell
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

## Demo accounts (local test data only)

Created by `backend/scripts/seed_demo.py`. These exist only in your local `backend/unitask.db`.

| Role | Email | Password |
| --- | --- | --- |
| Teacher | meera.iyer@example.edu | demo-teacher-2026 |
| Teacher | arjun.nair@example.edu | demo-teacher-2026 |
| Student | riya.sharma@example.edu | demo-student-2026 |
| Student | aditya.menon@example.edu | demo-student-2026 |
| Student | sneha.pillai@example.edu | demo-student-2026 |

To demo Teams, register **your own** student account (with any email), then connect your real college
Microsoft account from *Teams sync*. Teams data is never faked.

## A five-minute walkthrough

1. **The problem.** "Deadlines are spread across Teams, VTOP and WhatsApp. A dashboard that counts them doesn't help. You need to know what to do *now*."
2. **Teacher side** (meera.iyer). Open *Compiler Design* and show the join code. Post a new assignment with a handout. Open *Lab 4*: two students have turned in. Open a submission, download the file, grade it, and return it.
3. **Student side** (riya.sharma). *Today* leads with **Do this next**: the overdue ER diagram, since late work is still accepted. Below it, *Also pressing* gives a reason for each item, e.g. "Due in 44h · about 1h of work".
4. **Free-time planner.** Click **2h**. UniTask fills the time with the most urgent work and says what doesn't fit.
5. **Effort changes ranking.** Open *Revise Unit 3* and change effort from 4h to 30 min. Go back to Today: it drops down the list.
6. **Turn in and grade.** Open *Lab 4* and see the grade and feedback the teacher just returned.
7. **Teams.** Sign in as your own account → *Teams sync* → **Connect Microsoft Teams** → Microsoft sign-in. Your real Teams classes and assignments appear in *Classes* and *Today*, each linked back to Teams. Later syncs flag moved due dates and new assignments.
8. **Where AWS fits.** Files go to private S3 through presigned links, accounts can live in Cognito, and the next phase adds reminders. See `docs/AWS_PLAN.md`.

## Resetting

Stop the backend, delete `backend/unitask.db` and `backend/uploads/`, then run the seed script again.
