# Development

How to install, configure, run and test mta-system on your computer. For the server, see [deployment.md](deployment.md). Add each change to [HISTORY.rst](../HISTORY.rst).

## Setup

### Requirements

* Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and [Task](https://taskfile.dev/)
* Docker and Docker Compose, for the services of the users and the Docker setup

### Install

```bash
uv venv .venv
source .venv/bin/activate        # Windows: call .venv\Scripts\activate.bat
task app:install-dev             # dependencies and development tools
```

`task app:install` installs only what the app needs to run.

### Configure

```bash
task app:init-env
```

This copies the samples from `samples/` to `envs/` and `setup/` and keeps existing files. It also creates `envs/pgadmin4-proxy.env` from `samples/pgadmin4-proxy.env` with a random secret. Git and the Docker image do not include these folders.

Then change the values in `envs/webapp-dev-local.env`:

| Setting | Meaning |
| --- | --- |
| `SECRET_KEY` | Signs the session cookie. Use a long random value. |
| `HASH_KEY_LINKS`, `HASH_KEY_HIDDEN` | Keys for the login links and the captcha. Do not change `HASH_KEY_LINKS` after the first registration: the login links and PINs depend on it. |
| `COURSE_SECURITY_CODE` | Users need this code to register. |
| `SERVER_FQDN` | Name of the server for the users. |
| `SYSTEM_ADMINS` | E-mail addresses of the admins, separated by `;`. |
| `ALLOWED_FQDN_FOR_EMAILS` | E-mail domains that can register, for example `uol.de;uni-oldenburg.de`. List each subdomain. Empty: all domains. |
| `MTAS_DB_PATH` | SQLite file. Default: `data/mta-system.db`. |
| `MAIL_*` | SMTP server for the registration e-mail. |
| `TARGET_SERVER` | `development` or `production`. |
| `ENABLE_API_DOCS` | Switches the API docs on or off. See [API docs](#api-and-api-docs). |

`samples/webapp.env` lists all settings. The app takes each setting from the first of these places:

1. an environment variable
2. the env file in `ENV_FILE_NAME` (default: `envs/webapp-dev-local.env`, also for the `prod:` tasks)
3. the default in `app/config.py`

An empty value counts as "not set". A wrong value, for example `MAIL_PORT=abc`, stops the app with a message. To check your settings:

```bash
task app:config
ENV_FILE_NAME=envs/webapp-dev-docker.env task app:config
```

### Services for the users

The database stores in which services a new user gets an account. Change it on the admin page **Services → Auto creation**, or:

```bash
task app:cli -- auto-creation                                   # shows the switches
task app:cli -- auto-creation --on postgresql --on pgadmin4
```

* All services are off at the start. The app then runs without Docker and PostgreSQL.
* WordPress needs MariaDB: switch on MariaDB first.
* A change affects only new users.
* JupyterHub, NiFi and Superset are deprecated. The app creates no new accounts in them.
* Before version 2.0.0, the env file had `CREATE_<NAME>_SERVICE`. `task db:upgrade` copies these values into the database once. Then you can delete them.
* `SERVICES_UI` lists the services on the services page, separated by `;`. If you set it, add `sqlmate` and `surveylite` to show them.

### sqlmate (optional)

[sqlmate](https://github.com/vdmitriyev/sqlmate) gives SQL exercises to the students. The app creates the accounts through the API of sqlmate. The services page shows the address, a login link, the login and the PIN.

Settings of the app: `SQLMATE_API_URL`, `SQLMATE_API_KEY` (same as `API_KEY` in `envs/sqlmate-service.env`) and `SQLMATE_URL`.

To use it with `task dev:up`:

1. Get the image `sqlmate:<SQLMATE_VERSION>` (version in `versions.env`). To build it from `temp/sqlmate`: `task services:build-sqlmate`.
2. Change the values in `envs/sqlmate-service.env`.
3. Start it in the network of the development setup:

   ```bash
   SQLMATE_NETWORK=mta-system_mtas-network task sqlmate:up
   task sqlmate:init
   ```

All steps: [deployment.md](deployment.md#sqlmate-optional).

### SurveyLite (optional)

[SurveyLite](https://github.com/vdmitriyev/surveylite) (0.21.0 or newer) runs anonymous surveys. The app creates a participant for each user through the API of SurveyLite. Only the app table `surveylite_service` links a participant to a user.

* The services page shows the login link, the login, the PIN and the survey links. The survey links also log the user in.
* On the admin page **Services → SurveyLite**, an admin gives surveys to the users. An admin can also lock a service (for example sqlmate) until the user completes a survey.
* **New login link** on the admin page makes a new link. The old links stop working.
* Settings of the app: `SURVEYLITE_API_URL`, `SURVEYLITE_API_KEY` (one of `SURVEYLITE_API_KEYS` in `envs/surveylite-service.env`) and `SURVEYLITE_URL`. The app builds all links from `SURVEYLITE_URL`.

To use it with `task dev:up`:

1. Get the image `surveylite:<SURVEYLITE_VERSION>` (version in `versions.env`). To build it from `temp/surveylite`: `task services:build-surveylite`.
2. Change the values in `envs/surveylite-service.env`.
3. Start it in the network of the development setup:

   ```bash
   SURVEYLITE_NETWORK=mta-system_mtas-network task surveylite:up
   ```

All steps: [deployment.md](deployment.md#surveylite-optional).

### Create the database and run the app

```bash
task db:init      # creates the SQLite database and imports setup/initial_exercises.csv
task app:serve    # runs the app on http://127.0.0.1:5353 and reloads on code changes
```

`task setup` installs, creates the env files and the database in one step. `task` lists all tasks.

| Task | What it does |
| --- | --- |
| `task app:serve` | Runs the app with reload. Other port: `PORT=8000 task app:serve` |
| `task app:start` | Runs the app without reload. More workers: `WORKERS=4 task app:start` |
| `task app:cli -- <command>` | Runs a command of the app, see [Commands](#commands) |
| `task app:config` | Checks the settings and shows them without secrets |

### Run in Docker for development

The app runs with reload behind nginx, with PostgreSQL and pgAdmin 4. The settings come from `envs/webapp-dev-docker.env`.

```bash
task dev:up                   # builds and starts, app on http://127.0.0.1:5252
task dev:init                 # database, exercises, demo database
task dev:logs -- webapp       # logs of the app
task dev:cli -- show-config   # a command of the app in its container
task dev:down
task dev:app-recreate         # builds the app again, recreates only the app
task dev:nginx-recreate       # builds nginx again, recreates only nginx
task dev:nginx-reload         # checks the nginx configuration and reloads it
```

* Register with an address from `SYSTEM_ADMINS` to see the admin pages. To register the same address again, delete the user on the admin page **Users**.
* In development, the app writes the login link to the log. You do not need a mail server.
* The containers of the users need their images: `task services:pull-metabase` and `task services:build-openrefine`. After a change in `versions.env`, see [Versions of the services](deployment.md#versions-of-the-services).
* pgAdmin 4 runs at `https://127.0.0.1/pgadmin4/`, and directly at `http://127.0.0.1:5050` (port `8080` in the container). `envs/pgadmin4-proxy.env` is optional in development. See [deployment.md](deployment.md#pgadmin-4).
* After a change in `provision/nginx/nginx-docker.conf`, run `task dev:nginx-recreate`.
* After a change of the dependencies or the `Dockerfile`, run `task dev:app-recreate`. The app then needs a few seconds to start. Until then, nginx answers with 502.
* After a change in `app/models.py`, create and apply a migration: `task db:migrate -- -m "what changed"`.
* `setup/initial_exercises.csv` lists the exercises. Each exercise has a review part (`has_review`), a bonus part (`has_bonus`, `bonus_max_points`) or both.

### Commands

```bash
python -m app.cli --help
```

| Command | What it does |
| --- | --- |
| `db-upgrade` | Creates or updates the SQLite database |
| `db-migrate` | Creates a migration from the changes in the models |
| `import-data-exercises` | Imports the exercises from the CSV file |
| `create-demo-db` | Creates the demo database and a read-only user in PostgreSQL |
| `create-custom-db` | Creates a database with its own user in PostgreSQL |
| `grant-public-schema` | Lets all users create tables in their database |
| `nginx-config` | Creates the nginx parts for OpenRefine and NiFi |
| `show-config` | Shows the settings without secrets |
| `auto-creation` | Shows or changes the services of new users (`--on <service>`, `--off <service>`) |
| `check-mail` | Logs in to the SMTP server. `--to <address>` also sends a test e-mail |

## API and API docs

The pages are HTML. A small JSON API serves the scripts of the pages and the health check:

| Address | What it returns |
| --- | --- |
| `GET /api/health` | State and version of the app (for the Docker health check) |
| `GET /api/tasks/{id}` | State of a background task |
| `GET /api/services/status` | State of the containers of the logged-in user |

FastAPI shows docs for this API at `/docs`, `/redoc` and `/openapi.json`. They are on in development and off in production (404). `ENABLE_API_DOCS=true` or `false` sets them for both.

## Tests

```bash
task app:test                 # all tests
task app:test -- -k login     # tests with "login" in the name
task app:coverage             # lines of app/ that no test runs
```

The tests use a temporary SQLite database. They need no Docker, PostgreSQL or mail server.

The test copy runs the app with Docker and all services next to a real setup. It uses its own volumes, the app on `127.0.0.1:5354` and the database on `127.0.0.1:35433`. Its checks cover the pages, registration, login, dataset import and each service, also the pgAdmin 4 login through nginx. It builds sqlmate and SurveyLite from `temp/sqlmate` and `temp/surveylite`. `TESTENV_VARIANT=hostports` selects the second network variant.

```bash
task testenv:deploy                     # builds, starts and checks, then removes it
TESTENV_KEEP=true task testenv:deploy   # same, but keeps it running
task testenv:logs
task testenv:down                       # removes containers, volumes and the app image
```
