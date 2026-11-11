"""JSON API: health check and state of background tasks and containers"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.database import get_db
from app.models import CONTAINER_SERVICES, Users
from app.services import docker_ctl
from app.tasks import get_task, task_to_dict
from app.users import container_name, get_user_services
from app.web import require_user

router = APIRouter(prefix="/api", tags=["api"])


class Health(BaseModel):
    status: str
    version: str


class TaskState(BaseModel):
    id: str
    kind: str
    status: str
    message: str | None
    finished: bool


@router.get("/health", response_model=Health, summary="Checks that the app runs")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": __version__}


@router.get(
    "/tasks/{task_id}",
    response_model=TaskState,
    summary="Gets the state of a background task",
)
def task_state(task_id: str, db: Session = Depends(get_db)):
    task = get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="No such task")
    return task_to_dict(task)


@router.get(
    "/services/status",
    response_model=dict[str, str],
    summary="Gets the state of the containers of the logged-in user",
)
def services_status(db: Session = Depends(get_db), user: Users = Depends(require_user)):
    services = get_user_services(db, user.itid)
    names = {
        name: container_name(name, services[name])
        for name in CONTAINER_SERVICES
        if name in services
    }
    statuses = docker_ctl.container_statuses(list(names.values()))
    return {
        name: statuses.get(container, docker_ctl.UNKNOWN)
        for name, container in names.items()
    }
