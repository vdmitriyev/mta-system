"""Starts the entry points as the deployment does: in a new Python process"""

import os
import subprocess
import sys

import pytest

from app.config import BASE_DIR
from tests.conftest import BASE_ENV


@pytest.fixture
def run_python(tmp_path):
    def run(*args, **extra_env):
        env = {
            **os.environ,
            **BASE_ENV,
            "MTAS_DB_PATH": str(tmp_path / "entry.db"),
            "ENV_FILE_NAME": str(tmp_path / "no.env"),
            "PYTHONPATH": str(BASE_DIR),
            **extra_env,
        }
        return subprocess.run(
            [sys.executable, *args],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    return run


def test_cli_creates_the_database_and_writes_the_log(run_python, tmp_path):
    result = run_python("-m", "app.cli", "db-upgrade")
    assert result.returncode == 0, result.stderr
    assert "database is up to date" in result.stdout
    assert (tmp_path / "entry.db").exists()
    assert (tmp_path / ".logs" / "app-server.log").exists()


def test_run_module_creates_the_app(run_python):
    code = "import run; print(run.app.title, run.app.docs_url)"
    result = run_python("-c", code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("mta-system /docs")

    result = run_python("-c", code, TARGET_SERVER="production")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("mta-system None")


def test_missing_secret_stops_the_start_with_a_clear_message(run_python):
    result = run_python("-c", "import run", SECRET_KEY="", FLASK_SECRET_KEY="")
    assert result.returncode != 0
    assert "Set the environment variable SECRET_KEY" in result.stderr


def test_cli_names_a_wrong_setting(run_python):
    result = run_python("-m", "app.cli", "show-config", MAIL_PORT="abc")
    assert result.returncode == 1
    assert "Wrong settings: MAIL_PORT" in result.stderr
    assert "Traceback" not in result.stderr
