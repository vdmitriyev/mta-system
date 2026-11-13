# Development

How to install, configure, run and test the app on your computer. For the Docker image and the production server, see [deployment.md](deployment.md).

## Setup

### Requirements

* Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and [Task](https://taskfile.dev/)
* Docker and Docker Compose, if you want the services for the students or the Docker deployment

### Install

```bash
uv venv .venv
source .venv/bin/activate        # Windows: call .venv\Scripts\activate.bat
task app:install-dev             # dependencies and development tools from pyproject.toml
```

`task app:install` installs only what the app needs to run.

### Configure

```bash
task app:init-env
```

This copies the samples from `samples/` to `envs/` and `setup/`. Existing files are kept. Both folders are not in git and not in the Docker image. Then change the values in `envs/webapp-dev-local.env`:

| Setting | Meaning |
| --- | --- |
| `SECRET_KEY` | Signs the session cookie. Use a long random value. |
| `HASH_KEY_LINKS`, `HASH_KEY_HIDDEN` | Keys for the login links and the captcha. Do not change `HASH_KEY_LINKS` after the first registration: the login links and PINs depend on it. |
| `COURSE_SECURITY_CODE` | Users need this code to register. |
| `SERVER_FQDN` | Name of the server as the users see it. |
| `SYSTEM_ADMINS` | E-mail addresses with admin rights, separated by `;`. |
| `ALLOWED_FQDN_FOR_EMAILS` | E-mail domains that can register, e.g. `uol.de;uni-oldenburg.de`. Upper and lower case do not matter. Subdomains must be listed on their own. Empty: all domains. |
| `MTAS_DB_PATH` | SQLite file. Default: `data/mta-system.db`. |
| `MAIL_*` | SMTP server for the registration e-mail. |
| `TARGET_SERVER` | `development` or `production`. |
| `ENABLE_API_DOCS` | Switches the FastAPI docs on or off. See below. |

`samples/webapp.env` lists all settings. The app takes each setting from the first of these places:

1. an environment variable
2. the env file in `ENV_FILE_NAME` (default: `envs/webapp-dev-local.env`)
3. the default value in `app/config.py`

Empty values count as "not set". The app checks the values on start. A wrong value, for example `MAIL_PORT=abc`, stops the start with a message that names the variable. To check your settings:

```bash
task app:config                                       # envs/webapp-dev-local.env
ENV_FILE_NAME=envs/webapp-dev-docker.env task app:config
```

### Services for the users

In which services a new user gets an account (PostgreSQL, pgAdmin 4, Metabase, ...) is not in the env file. It is stored in the database. An admin changes it on the page **Admin → Services → Auto creation**, or on the command line:

```bash
task app:cli -- auto-creation                                   # shows the switches
task app:cli -- auto-creation --on postgresql --on pgadmin4
```

JupyterHub, NiFi and Superset are deprecated: the app creates no new accounts in them.

All services are switched off at the start. The app then runs on its own, without Docker and without PostgreSQL. WordPress needs MariaDB: switch on MariaDB first. A change affects only new users.

### sqlmate and SurveyLite

[sqlmate](https://github.com/vdmitriyev/sqlmate) (SQL exercises) and [SurveyLite](https://github.com/vdmitriyev/surveylite) (anonymous surveys) run as shared services in Docker (`compose.services.yml`). The app creates the accounts through their APIs.

* **sqlmate**: each user gets an account with the internal e-mail of the user. The services page shows the address, a personal login link, the login and the PIN. Admin page: **Services → sqlmate**.
* **SurveyLite** (version 0.21.0 or newer): each user gets an anonymous participant. SurveyLite does not know who the participant is: only the table `surveylite_service` of the app links them. The services page shows the link to `/me` of SurveyLite, a personal login link (`/me?auth=…`), the login, the PIN and the survey links of the user. The survey links also log the user in, so they open surveys that need a login (`require_login`). If a login link becomes known to others, **New login link** on the admin page makes a new one: the old links stop working.
* On the admin page **Services → SurveyLite**, an admin gives surveys to the users and chooses services that open only after a completed survey (for example sqlmate). Until then, the services page shows the survey instead of the login of the service. A new user gets these surveys at once.
* Settings of the app: `SQLMATE_API_URL`, `SQLMATE_API_KEY`, `SQLMATE_URL`, `SURVEYLITE_API_URL`, `SURVEYLITE_API_KEY` and `SURVEYLITE_URL` (see `samples/webapp.env`).
* If `SERVICES_UI` is set in your env file, add `sqlmate` and `surveylite` to it.

Before version 2.0.0, the env file had the settings `CREATE_<NAME>_SERVICE`. `task db:upgrade` copies their values into the database once. After that, the app ignores them and you can delete them from the env file.

### Create the database and run the app

```bash
task db:init      # creates the SQLite database and imports setup/initial_exercises.csv
task app:serve    # runs the app on http://127.0.0.1:5353 and reloads on code changes
```

`task setup` does the install, the env files and the database in one step.

| Task | What it does |
| --- | --- |
| `task app:serve` | Runs the app and reloads on code changes. Other port: `PORT=8000 task app:serve` |
| `task app:start` | Runs the app without reload, as in production. More workers: `WORKERS=4 task app:start` |
| `task app:cli -- <command>` | Runs a command of the app, see [Commands](#commands) |
| `task app:config` | Checks the settings and shows them without passwords and keys |

### Run in Docker for development

The app (with reload) runs behind nginx, together with PostgreSQL, pgAdmin 4, Metabase and OpenRefine. The settings come from `envs/webapp-dev-docker.env`.

```bash
task dev:up                   # builds and starts, app on http://127.0.0.1:5252
task dev:init                 # database, exercises, demo database
task dev:logs -- webapp       # logs of the app
task dev:cli -- show-config   # a command of the app in its container
task dev:down
```

* Register with an e-mail address from `SYSTEM_ADMINS` to get the admin pages.
* In development mode, the app writes the login link of a registration to the log. You do not need a mail server to try the app.
* `setup/initial_exercises.csv` lists the exercises of the course. Each exercise has a review part (`has_review`) and/or a bonus part (`has_bonus`, `bonus_max_points`).
* After a change in `app/models.py`, run `task db:migrate -- -m "what changed"` to create and apply a migration.
* Run `task` to see all tasks.

### Commands

```bash
python -m app.cli --help
```

| Command | What it does |
| --- | --- |
| `db-upgrade` | Creates the SQLite database or updates it |
| `db-migrate` | Creates a migration from the changes in the models |
| `import-data-exercises` | Imports the exercises from the CSV file |
| `create-demo-db` | Creates the demo database and a read-only user in PostgreSQL |
| `create-custom-db` | Creates a database with its own user in PostgreSQL |
| `grant-public-schema` | Lets all users create tables in their database |
| `nginx-config` | Creates the nginx config parts for OpenRefine and NiFi |
| `show-config` | Shows the env file and the settings without passwords and keys |
| `auto-creation` | Shows or changes in which services new users get an account (`--on <service>`, `--off <service>`) |
| `check-mail` | Connects and logs in to the SMTP server (`MAIL_*`). `--to <address>` also sends a test e-mail |

## API and API docs

The pages are HTML. A small JSON API serves the scripts of the pages and health checks:

| Address | What it returns |
| --- | --- |
| `GET /api/health` | State and version of the app (used by the Docker health check) |
| `GET /api/tasks/{id}` | State of a background task |
| `GET /api/services/status` | State of the containers of the logged-in user |

FastAPI creates docs for this API at `/docs` (Swagger UI), `/redoc` and `/openapi.json`.

* In development, the docs are **on**.
* In production (`TARGET_SERVER=production`), the docs are **off**: the three addresses answer with 404.
* `ENABLE_API_DOCS=true` or `ENABLE_API_DOCS=false` sets it for both modes.

## Tests

```bash
task app:test                 # all tests
task app:test -- -k login     # tests with "login" in the name
task app:coverage             # shows the lines of app/ that no test runs
```

The tests use a temporary SQLite database. They do not need Docker, PostgreSQL or a mail server: these are replaced by test doubles.

To try the app with Docker and the services, use the test copy. It runs the app, PostgreSQL, pgAdmin 4, MariaDB and the containers of a user (Metabase, OpenRefine, WordPress) next to a real deployment (app on `127.0.0.1:5354`, database on `127.0.0.1:35433`, own volumes, containers named `mtas-testenv-...`). `TESTENV_VARIANT=hostports` selects the second network variant.

```bash
task testenv:deploy   # builds, starts and checks (pages, registration, login, dataset import, services), then removes it
TESTENV_KEEP=true task testenv:deploy   # same, but leaves it running
task testenv:logs
task testenv:down     # removes containers, volumes and the app image
```
