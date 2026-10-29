import asyncio
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).with_name(".env"))

from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app import jobs, models  # noqa: E402,F401 — register models before migrations
from app import teams  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app.migrate import upgrade_database  # noqa: E402
from app.routers import (  # noqa: E402
    assignments,
    auth,
    courses,
    exams,
    home,
    imports,
    integrations,
    library,
    planner,
    recovery,
    study,
    subjects,
    work,
)
from app.routes import router as timetable_router  # noqa: E402

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("unitask")

# Jobs the scheduler (the in-process loop below, or EventBridge Scheduler in AWS) may trigger.
CRON_JOBS = {"sync_all", "reminders"}


def _minutes(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


async def _scheduler_loop() -> None:
    """In-process scheduler for a single server. In AWS, set SCHEDULER=external and use /internal/cron."""
    sync_every = teams.auto_sync_minutes()
    remind_every = _minutes("REMINDER_MINUTES", 30)
    elapsed = 0
    while True:
        await asyncio.sleep(60)
        elapsed += 1
        for kind, every in (("sync_all", sync_every), ("reminders", remind_every)):
            if every and elapsed % every == 0:
                try:
                    await asyncio.to_thread(jobs.run, kind, {})
                except Exception:  # noqa: BLE001 — logged by jobs.run; keep the loop alive
                    pass


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("RUN_MIGRATIONS", "true").lower() != "false":
        revision = upgrade_database(engine)
        logger.info("Database schema at revision %s.", revision)
    if os.getenv("SEED_DEMO", "false").lower() == "true":
        from app.demo_seed import refresh

        with SessionLocal() as db:
            if refresh(db):
                logger.info("Synthetic demo workspace created or updated (SEED_DEMO=true).")
    jobs.register_all()
    task = None
    if os.getenv("SCHEDULER", "internal").lower() == "internal":
        task = asyncio.create_task(_scheduler_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="UniTask API",
    description="The student's academic operating system: deadlines, planning, materials, exams, revision and a tutor.",
    version="3.0.0",
    lifespan=lifespan,
)

allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in allowed_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    courses.router,
    work.router,
    assignments.router,
    home.router,
    subjects.router,
    library.router,
    exams.router,
    planner.router,
    recovery.router,
    study.router,
    imports.router,
    integrations.router,
    timetable_router,
):
    app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.post("/internal/cron/{job}", include_in_schema=False, status_code=202)
def cron(job: str, x_cron_secret: str = Header(default="")) -> dict[str, str]:
    """Entry point for EventBridge Scheduler (via a tiny Lambda or API destination)."""
    secret = os.getenv("CRON_SECRET", "")
    if not secret or job not in CRON_JOBS:
        raise HTTPException(404, "Not found.")
    if not hmac.compare_digest(x_cron_secret, secret):
        raise HTTPException(403, "Forbidden.")
    return {"job": job, "queued": jobs.enqueue(job, {})}


# The built React app (frontend/dist), copied into the image as backend/static. Served from the same origin as
# the API, so the browser never needs CORS. Unknown paths fall back to index.html for client-side routing.
STATIC_DIR = Path(os.getenv("STATIC_DIR", str(Path(__file__).with_name("static")))).resolve()
if (STATIC_DIR / "index.html").is_file():
    if (STATIC_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def single_page_app(path: str):
        if path.startswith(("api/", "internal/")):
            raise HTTPException(404, "Not found.")
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(STATIC_DIR):
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
