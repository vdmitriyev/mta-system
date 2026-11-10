## About

**mta-system** (**m**odular **t**eaching **a**ssistance **system**) was designed to help students to acquire new hands-on software experience. The solution was designed to be modular by design and to be hosted by a lecturer/faculty member for students.

## Dependencies

* Python 3.12 or newer
    + Dependencies: `pyproject.toml`
* Docker + Docker Compose

## Documentation

Documentation is available [here](https://vdmitriyev.github.io/mta-system/)

## Architecture

## Setup

The mta-system stores its own data (users, exercises, reviews, bonus points, settings) in a SQLite database.
PostgreSQL is only used as a service for the students (optional, see `CREATE_POSTGRESQL_SERVICE`).

### Requirements

* Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and [Task](https://taskfile.dev/)
* A TrueType font for the captcha on the registration page (Ubuntu/Debian: `sudo apt install fonts-freefont-ttf`)

### Create the virtual environment

```bash
task app:install                 # installs the dependencies from pyproject.toml into .venv
source .venv/bin/activate
```

* `task app:install-dev` also installs the development tools (pytest, black, pre-commit, ...).

### Configure

* The app reads its settings from the file in `ENV_FILE_NAME` (default: `envs/webapp-dev-local.env`).
* The env files are in the folder `envs/` (not in git and not in the Docker image). Use `envs/sample-dev-docker.env` as a template.
* `MTAS_DB_PATH` sets the SQLite file (default: `data/mta-system.db`, relative to the project folder).
* Admin rights: put your e-mail in `SYSTEM_ADMINS`.

### Create the database and run the app

```bash
task db:init      # creates the SQLite database and imports the exercises from setup/initial_exercises.csv
task app:serve    # runs the app on http://127.0.0.1:5353
```

* `setup/initial_exercises.csv` lists the exercises of the course. Each exercise has a review part (`has_review`) and/or a bonus part (`has_bonus`, `bonus_max_points`). Reviews and bonus points are stored per exercise and user.
* On start, the app adds the default UI visibility settings (`app/main/shared_helpers.py`) that are not in the database yet. Changes made in the admin UI are kept.
* After a change in `app/models.py`, run `task db:migrate` to create and apply a new migration.
* Run `task` to see all tasks.

### Docker

```bash
task app:build-image   # builds mta-system:latest
```

* On start, the container applies the migrations and imports the initial data, then runs gunicorn on port `5151`.
* Mount `/mta-system/data` (SQLite database) and `/mta-system/.logs` as volumes.
* To start and stop the service containers, the app needs `/var/run/docker.sock`.

## System UI

* User view. It is user by an user user to get access to the features of the system such as - services credentials, datasets imports, start/stop for services

* Admin view. It is used by an admin to monitor various parameters of a server - CPU usage, RAM usage, amount of containers running, logs, etc.

### Citing - BibTeX

```bibtex
@inproceedings{Dmitriyev:2021:HandOn,
	title        = {Enable students to acquire new hands-on software experience using the modular teaching assistance system},
	author       = {Dmitriyev, Viktor and Jan{\ss}en, Christian and Solsbach, Andreas},
	year         = 2021,
	booktitle    = {INFORMATIK 2021},
	publisher    = {Gesellschaft für Informatik, Bonn},
	pages        = {91--101},
	doi          = {10.18420/informatik2021-006},
	isbn         = {978-3-88579-708-1},
	url          = {https://dl.gi.de/items/aeac2dcb-1442-4c38-ae90-64e9730c6ce9},
	pissn        = {1617-5468}
}
```

## License

* Source Code - MIT
* Datasets - license is found directly inside the import module/dataset itself
