"""Long-running jobs, run with the background tasks of FastAPI.

A job runs in the worker process after the response was sent. Its state is
stored in the table "background_tasks", so every worker can report it.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import psutil
from fastapi import BackgroundTasks
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import session_scope
from app.models import BackgroundTask

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"
ACTIVE = (QUEUED, RUNNING)

# A job that is still active after this time is stopped (a service did not answer)
STALE_AFTER = timedelta(minutes=30)
LOST_MESSAGE = "The server stopped while the task was running. Start it again."
STALE_MESSAGE = "The task took too long. A service did not answer. Try again later."

logger = logging.getLogger(__name__)


class TaskError(Exception):
    """Stops a job. The text is shown to the user."""


def enqueue(
    background_tasks: BackgroundTasks,
    db: Session,
    kind: str,
    func: Callable,
    *args,
    user_id: int | None = None,
) -> BackgroundTask:
    """Registers a job and runs func(db, *args) after the response.

    func returns the text to show when the job is done (or None).
    """

    task = BackgroundTask(
        public_id=uuid.uuid4().hex, kind=kind, user_id=user_id, status=QUEUED
    )
    db.add(task)
    db.commit()
    background_tasks.add_task(run_task, task.public_id, func, *args)
    return task


def run_task(public_id: str, func: Callable, *args) -> None:
    with session_scope() as db:
        _set_state(
            db,
            public_id,
            status=RUNNING,
            started_at=datetime.now(),
            worker_pid=os.getpid(),
        )
        try:
            message = func(db, *args)
            status = DONE
        except TaskError as error:
            db.rollback()
            message, status = str(error), FAILED
        except Exception:
            db.rollback()
            logger.exception("Background task failed: %s", public_id)
            message, status = "The task failed with an error on the server", FAILED
        _set_state(
            db, public_id, status=status, message=message, finished_at=datetime.now()
        )


def _set_state(db: Session, public_id: str, **values) -> None:
    db.execute(
        update(BackgroundTask)
        .where(BackgroundTask.public_id == public_id)
        .values(**values)
    )
    db.commit()


def get_task(db: Session, public_id: str) -> BackgroundTask | None:
    fail_stale_tasks(db)
    return db.query(BackgroundTask).filter_by(public_id=public_id).first()


def active_task(db: Session, kind: str, user_id: int) -> BackgroundTask | None:
    """Gets the newest job of this kind that the user still waits for"""

    fail_stale_tasks(db)
    return (
        db.query(BackgroundTask)
        .filter(
            BackgroundTask.kind == kind,
            BackgroundTask.user_id == user_id,
            BackgroundTask.status.in_(ACTIVE),
        )
        .order_by(BackgroundTask.itid.desc())
        .first()
    )


def recent_tasks(db: Session, limit: int = 50) -> list:
    fail_stale_tasks(db)
    return (
        db.query(BackgroundTask).order_by(BackgroundTask.itid.desc()).limit(limit).all()
    )


def fail_stale_tasks(db: Session) -> int:
    """Marks lost and too long jobs as failed. Returns the number of these jobs.

    Lost: the worker process that ran the job is gone (restart, crash).
    Too long: the job is active for longer than STALE_AFTER.
    """

    # created_at is set by SQLite, in UTC
    limit = datetime.now(timezone.utc).replace(tzinfo=None) - STALE_AFTER
    lost, stale = [], []
    active = db.query(
        BackgroundTask.itid,
        BackgroundTask.status,
        BackgroundTask.worker_pid,
        BackgroundTask.created_at,
    ).filter(BackgroundTask.status.in_(ACTIVE))
    for itid, status, worker_pid, created_at in active:
        if status == RUNNING and worker_pid and not psutil.pid_exists(worker_pid):
            lost.append(itid)
        elif created_at is not None and created_at < limit:
            stale.append(itid)
    # write only if needed: a write keeps SQLite locked until the commit
    if not lost and not stale:
        return 0

    for ids, message in ((lost, LOST_MESSAGE), (stale, STALE_MESSAGE)):
        if ids:
            db.execute(
                update(BackgroundTask)
                .where(BackgroundTask.itid.in_(ids), BackgroundTask.status.in_(ACTIVE))
                .values(status=FAILED, message=message, finished_at=datetime.now())
            )
    db.commit()
    count = len(lost) + len(stale)
    logger.warning("%s background tasks were marked as failed", count)
    return count


def task_to_dict(task: BackgroundTask) -> dict:
    return {
        "id": task.public_id,
        "kind": task.kind,
        "status": task.status,
        "message": task.message,
        "finished": task.status not in ACTIVE,
    }
