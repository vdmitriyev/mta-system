## About

**mta-system** (**m**odular **t**eaching **a**ssistance **system**) helps students to get hands-on experience with software. A lecturer hosts it for a course. Students register and get their own access to services such as PostgreSQL, pgAdmin 4, Metabase and OpenRefine.

What the web app does:

* **Students** register with their e-mail address and a course code. They see the address, login and password of each of their services, start their containers, import sample datasets, and read reviews and bonus points for their exercises.
* **Admins** write reviews and bonus points, manage the databases, logins and containers of the users (menu **Services**: PostgreSQL, pgAdmin 4, Metabase, OpenRefine), check the OpenRefine logins, prepare accounts in advance, choose which parts of the UI are visible, and watch the server (CPU, memory, containers, logs).

The pages have a light and a dark theme. The button in the header switches between them. The browser stores the choice. Without a choice, the system setting decides.

Documentation is available [here](https://vdmitriyev.github.io/mta-system/).

## Architecture

| Part | Technology |
| --- | --- |
| Web app | [FastAPI](https://fastapi.tiangolo.com/) with Jinja2 templates, served by uvicorn |
| Data of the app | SQLite (users, exercises, reviews, bonus points, settings), migrations with Alembic |
| Long-running jobs | Background tasks of FastAPI. Their state is in the table `background_tasks`. No Redis and no extra worker process. |
| Services for the students | Docker containers (one per user for Metabase, OpenRefine, NiFi, WordPress), PostgreSQL (set up with [dbsetupmate](https://pypi.org/project/dbsetupmate/)), MariaDB |
| Entry point in production | nginx (HTTPS, basic auth for the service containers) |

```
app/
  app.py            creates the FastAPI app (middleware, error pages, API docs switch)
  config.py         settings from environment variables
  routers/          pages (public, account, admin) and the JSON API
  tasks.py          background tasks
  users.py          login data and registration
  provisioning.py   creates the accounts of a user in the services
  services/         PostgreSQL, MariaDB, Docker, Metabase, OpenRefine, ...
  importers/        sample datasets for the PostgreSQL database of a user
  cli/              commands: python -m app.cli <command>
  templates/        HTML pages
  static/           stylesheet, script, images (no files from a CDN)
migrations/         Alembic migrations of the SQLite database
samples/            templates for the env files and the exercises
tests/              automated tests, tests/testenv/ is the Docker test copy
```

Registration, dataset imports and the setup of containers can take minutes. The app starts them as background tasks and answers at once. The page then asks `/api/tasks/<id>` for the state and shows the result. A task fails if its worker process stops (for example on a restart) or if it runs for more than 30 minutes, so a page does not wait forever.

Metabase and OpenRefine run in one container per user. Before the app creates one, it checks that the image is on the server or in the registry.

### Versions of the services

The versions of the service images are in one file, `versions.env` in the project folder:

```ini
# containers for each user
METABASE_VERSION=v0.57.3      # metabase/metabase:<version> from Docker Hub
OPENREFINE_VERSION=3.10.1     # openrefine:<version>, built on the server from provision/openrefine
WORDPRESS_VERSION=latest      # wordpress:<version> from Docker Hub
WORDPRESS_CLI_VERSION=cli     # wordpress:<tag>, the installer (WP-CLI) that the app starts
# shared services
POSTGRESQL_VERSION=17.11      # postgres:<version> from Docker Hub
PGADMIN4_VERSION=8.12         # dpage/pgadmin4:<version> from Docker Hub
MARIADB_VERSION=13.0.2        # mariadb:<version> from Docker Hub, for WordPress
```

These read the same file:

| Who | How |
| --- | --- |
| the web app | as an env file with the lowest priority: a variable in the environment or in the env file of the app wins |
| all `task` commands | `dotenv` in `Taskfile.yaml`, e.g. for the docker compose calls |
| `compose.services.yml`, `tests/testenv/compose.yaml`, `provision/wordpress/docker-compose.yml` | `task dev:up`, `task prod:up`, `task testenv:deploy`, or `docker compose --env-file versions.env ...`. Without the file, compose stops with a message. |

The admin page **Services → Auto creation** shows the versions, `task services:versions` too. The page **Services → PostgreSQL** compares the version that the server runs with `POSTGRESQL_VERSION`.

To change a version:

1. Change it in `versions.env`.
2. Get the image on the server: `task services:pull-metabase`, `task services:build-openrefine`, `task services:pull-wordpress`, `task services:pull-postgresql`, `task services:pull-pgadmin4` or `task services:pull-mariadb`. `task services:update-all` gets all of them.
3. Restart the app. The admin page of the service shows if the image is on the server.
4. New users get the new version. For an existing user, use "Create again" on the admin page of the service. For PostgreSQL and pgAdmin 4, restart the service: `task prod:up`. For MariaDB, restart `provision/wordpress/docker-compose.yml` with `--env-file versions.env`.

A new major version of PostgreSQL (for example 15 to 17) cannot open the data of the old one. Dump the databases before the change and restore them afterwards. MariaDB cannot go back to an older version once a newer one wrote the data.

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

All services are switched off at the start. The app then runs on its own, without Docker and without PostgreSQL. WordPress needs MariaDB: switch on MariaDB first. A change affects only new users.

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

To try the app with Docker and a real PostgreSQL database, use the test copy. It runs next to a real deployment (app on `127.0.0.1:5354`, database on `127.0.0.1:35433`, own volumes):

```bash
task testenv:deploy   # builds, starts and checks: pages, registration, login, dataset import
task testenv:logs
task testenv:down     # removes containers, volumes and the app image
```

## Deployment with Docker

```bash
task app:build-image   # builds mta-system:latest
```

* On start, the container applies the migrations and imports the exercises. Then it runs uvicorn on port `5151`.
* `WEB_CONCURRENCY` sets the number of worker processes (default: 4).
* Mount `/mta-system/data` (SQLite database) and `/mta-system/.logs` as volumes.
* To start and stop the service containers, the app needs `/var/run/docker.sock`.

### Production

```bash
cp samples/webapp.env envs/.env        # then set TARGET_SERVER=production and your values
task prod:up                           # app, nginx and the services
task prod:cert -- mtas.example.org     # Let's Encrypt certificate
task prod:logs
```

Before you go live:

1. Set `TARGET_SERVER=production`. This switches off the debug pages and the API docs, and makes the session cookie HTTPS-only.
2. Use new random values for `SECRET_KEY`, `HASH_KEY_LINKS` and `HASH_KEY_HIDDEN`, and for all passwords in `envs/`.
3. Set `SERVER_FQDN`, `SYSTEM_ADMINS`, `ALLOWED_FQDN_FOR_EMAILS` and the `MAIL_*` settings.
4. Keep the app behind nginx. Only nginx publishes ports to all interfaces (`80`, `443`). All other ports are bound to `127.0.0.1`.
5. Back up the folder `data/` (SQLite database) and `.htpasswd_nginx/`.

## Citing - BibTeX

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
