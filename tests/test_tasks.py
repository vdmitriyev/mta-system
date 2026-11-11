import os
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks

from app import tasks
from app.models import BackgroundTask
from app.tasks import TaskError, active_task, enqueue, fail_stale_tasks, get_task
from tests.conftest import add_user


def run(db, func, *args, **kwargs):
    """Registers a task and runs it, as FastAPI does after the response"""

    background = BackgroundTasks()
    task = enqueue(background, db, "test", func, *args, **kwargs)
    assert task.status == tasks.QUEUED
    for job in background.tasks:
        job.func(*job.args, **job.kwargs)
    db.expire_all()
    return get_task(db, task.public_id)


def test_task_that_succeeds(db):
    task = run(db, lambda _db, name: f"hello {name}", "world")
    assert task.status == tasks.DONE
    assert task.message == "hello world"
    assert task.started_at and task.finished_at


def test_task_error_is_shown_to_the_user(db):
    def job(_db):
        raise TaskError("no database")

    task = run(db, job)
    assert task.status == tasks.FAILED
    assert task.message == "no database"


def test_unexpected_error_is_hidden(db):
    def job(_db):
        raise RuntimeError("secret detail")

    task = run(db, job)
    assert task.status == tasks.FAILED
    assert "secret detail" not in task.message


def test_task_gets_its_own_database_session(db):
    seen = []
    run(db, lambda task_db: seen.append(task_db))
    assert seen[0] is not db


def test_active_task_is_found_until_it_is_finished(db):
    user = add_user(db)
    background = BackgroundTasks()
    task = enqueue(
        background, db, "import:flights", lambda _db: None, user_id=user.itid
    )
    assert active_task(db, "import:flights", user.itid).itid == task.itid
    assert active_task(db, "import:airbnb", user.itid) is None

    background.tasks[0].func(*background.tasks[0].args)
    db.expire_all()
    assert active_task(db, "import:flights", user.itid) is None


def test_recent_tasks_are_newest_first(db):
    for kind in ("a", "b", "c"):
        enqueue(BackgroundTasks(), db, kind, lambda _db: None)
    assert [task.kind for task in tasks.recent_tasks(db, limit=2)] == ["c", "b"]


def test_stale_tasks_are_marked_as_failed(db):
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    db.add(
        BackgroundTask(public_id="old", kind="x", status=tasks.RUNNING, created_at=old)
    )
    db.add(
        BackgroundTask(public_id="done", kind="x", status=tasks.DONE, created_at=old)
    )
    db.add(BackgroundTask(public_id="new", kind="x", status=tasks.QUEUED))
    db.commit()

    assert fail_stale_tasks(db) == 1
    db.expire_all()
    assert get_task(db, "old").status == tasks.FAILED
    assert get_task(db, "done").status == tasks.DONE
    assert get_task(db, "new").status == tasks.QUEUED


def test_task_to_dict(db):
    task = run(db, lambda _db: "ok")
    data = tasks.task_to_dict(task)
    assert data == {
        "id": task.public_id,
        "kind": "test",
        "status": "done",
        "message": "ok",
        "finished": True,
    }


def test_task_of_a_lost_worker_fails(db):
    alive = BackgroundTask(
        public_id="alive", kind="x", status=tasks.RUNNING, worker_pid=os.getpid()
    )
    # a process number that is not in use
    lost = BackgroundTask(
        public_id="lost", kind="x", status=tasks.RUNNING, worker_pid=2**22 + 7
    )
    db.add_all([alive, lost])
    db.commit()

    assert get_task(db, "lost").status == tasks.FAILED
    assert get_task(db, "lost").message == tasks.LOST_MESSAGE
    assert get_task(db, "alive").status == tasks.RUNNING


def test_task_that_runs_too_long_fails(db):
    user = add_user(db)
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=31)
    db.add(
        BackgroundTask(
            public_id="slow",
            kind="import:flights",
            user_id=user.itid,
            status=tasks.RUNNING,
            worker_pid=os.getpid(),
            created_at=old,
        )
    )
    db.commit()
    # the page shows no spinner: the task is no longer active
    assert active_task(db, "import:flights", user.itid) is None
    assert get_task(db, "slow").message == tasks.STALE_MESSAGE


def test_running_task_knows_its_worker(db):
    seen = []

    def job(job_db):
        task = job_db.query(BackgroundTask).one()
        seen.append(task.worker_pid)

    run(db, job)
    assert seen == [os.getpid()]
