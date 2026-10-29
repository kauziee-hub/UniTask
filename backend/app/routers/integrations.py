import json
import logging
import os
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import teams
from ..database import get_db
from ..models import Connection, Course, Coursework, User
from ..schemas import ConnectResponse, TeamsStatus
from ..security import require_student
from ..services import serve_local_file

router = APIRouter(prefix="/api", tags=["integrations"])
logger = logging.getLogger(__name__)


def _status(db: Session, user: User) -> TeamsStatus:
    connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == teams.PROVIDER))
    return TeamsStatus(
        configured=teams.settings() is not None,
        status=connection.status if connection else "not_connected",
        account=connection.account_label if connection else None,
        last_synced_at=connection.last_synced_at if connection else None,
        last_error=connection.last_error if connection else None,
        last_result=json.loads(connection.last_result) if connection and connection.last_result else None,
        auto_sync_minutes=teams.auto_sync_minutes(),
    )


@router.get("/integrations/teams", response_model=TeamsStatus)
def teams_status(user: User = Depends(require_student), db: Session = Depends(get_db)) -> TeamsStatus:
    return _status(db, user)


@router.post("/integrations/teams/connect", response_model=ConnectResponse)
def teams_connect(user: User = Depends(require_student), db: Session = Depends(get_db)) -> ConnectResponse:
    try:
        return ConnectResponse(auth_url=teams.begin_connect(db, user))
    except teams.TeamsError as exc:
        raise HTTPException(503, str(exc)) from exc


def _finish_connect(db: Session, params: dict[str, str]) -> str:
    user, outcome = teams.complete_connect(db, params)
    if user is not None and outcome == "connected":
        connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == teams.PROVIDER))
        try:
            teams.sync_connection(db, connection)
            outcome = "synced"
        except teams.TeamsError as exc:
            outcome = exc.status
    return outcome


@router.api_route("/integrations/teams/callback", methods=["GET", "POST"], include_in_schema=False)
async def teams_callback(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    """Microsoft redirects here after sign-in (form_post, so normally a POST)."""
    params = dict(request.query_params)
    if request.method == "POST":
        params.update({key: str(value) for key, value in (await request.form()).items()})
    outcome = await run_in_threadpool(_finish_connect, db, params)
    config = teams.settings()
    frontend = config.frontend_url if config else os.getenv("FRONTEND_URL", "http://localhost:5173")
    return RedirectResponse(f"{frontend}/connections?{urlencode({'teams': outcome})}", status_code=303)


@router.post("/integrations/teams/sync", response_model=TeamsStatus)
def teams_sync(user: User = Depends(require_student), db: Session = Depends(get_db)) -> TeamsStatus:
    connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == teams.PROVIDER))
    if connection is None or not connection.token_cache:
        raise HTTPException(409, "Connect Microsoft Teams first.")
    try:
        teams.sync_connection(db, connection)
    except teams.TeamsError:
        pass  # The status endpoint carries the error for the UI.
    return _status(db, user)


@router.delete("/integrations/teams", status_code=204)
def teams_disconnect(
    remove_items: bool = False, user: User = Depends(require_student), db: Session = Depends(get_db)
) -> Response:
    connection = db.scalar(select(Connection).where(Connection.user_id == user.id, Connection.provider == teams.PROVIDER))
    if connection is not None:
        db.delete(connection)
    if remove_items:
        for work in db.scalars(select(Coursework).where(Coursework.owner_id == user.id, Coursework.source == "teams")):
            db.delete(work)
        for course in db.scalars(select(Course).where(Course.owner_id == user.id, Course.source == "teams")):
            db.delete(course)
    db.commit()
    return Response(status_code=204)


@router.get("/files/{token}", include_in_schema=False)
def local_file(token: str):
    return serve_local_file(token)
