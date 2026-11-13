## About

**mta-system** (**m**odular **t**eaching **a**ssistance **system**) helps students to get hands-on experience with software. A lecturer hosts it for a course. Students register and get their own access to services such as PostgreSQL, pgAdmin 4, Metabase and OpenRefine, and optionally to SQL exercises ([sqlmate](https://github.com/vdmitriyev/sqlmate)) and anonymous surveys ([SurveyLite](https://github.com/vdmitriyev/surveylite)).

What the web app does:

* **Students** register with their e-mail address and a course code. They see the address, login and password of each of their services, start their containers, import sample datasets, and read reviews and bonus points for their exercises.
* **Admins** write reviews and bonus points, manage the databases, logins and containers of the users (menu **Services**: PostgreSQL, pgAdmin 4, Metabase, OpenRefine), check the OpenRefine logins, prepare accounts in advance, delete users (the e-mail address can then register again), choose which parts of the UI are visible, and watch the server (CPU, memory, containers, logs).

The pages have a light and a dark theme. The button in the header switches between them. The browser stores the choice. Without a choice, the system setting decides.

Documentation is available [here](https://vdmitriyev.github.io/mta-system/).

| Guide | Content |
| --- | --- |
| [docs/development.md](docs/development.md) | Install, settings, run the app, Docker for development, commands, API, tests |
| [docs/deployment.md](docs/deployment.md) | Docker image, production server, HTTPS certificate and nginx, delete users, sqlmate and SurveyLite, change the versions of the services |

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
docs/               development and deployment guides
migrations/         Alembic migrations of the SQLite database
samples/            templates for the env files and the exercises
tests/              automated tests, tests/testenv/ is the Docker test copy
```

Registration, dataset imports and the setup of containers can take minutes. The app starts them as background tasks and answers at once. The page then asks `/api/tasks/<id>` for the state and shows the result. A task fails if its worker process stops (for example on a restart) or if it runs for more than 30 minutes, so a page does not wait forever.

Metabase and OpenRefine run in one container per user. Before the app creates one, it checks that the image is on the server or in the registry.

## Supported versions of the services

The versions are in `versions.env`. To change one, see [Versions of the services](docs/deployment.md#versions-of-the-services).

| Service | Image | Version | Variable in `versions.env` |
| --- | --- | --- | --- |
| Metabase (one container per user) | `metabase/metabase` from Docker Hub | `v0.57.3` | `METABASE_VERSION` |
| OpenRefine (one container per user) | `openrefine`, built on the server from `provision/openrefine` | `3.10.1` | `OPENREFINE_VERSION` |
| WordPress (one container per user) | `wordpress` from Docker Hub | `latest` | `WORDPRESS_VERSION` |
| WP-CLI (installer of WordPress) | `wordpress` from Docker Hub | `cli` | `WORDPRESS_CLI_VERSION` |
| PostgreSQL (shared) | `postgres` from Docker Hub | `17.11` | `POSTGRESQL_VERSION` |
| pgAdmin 4 (shared) | `dpage/pgadmin4` from Docker Hub | `8.12` | `PGADMIN4_VERSION` |
| MariaDB (shared, for WordPress) | `mariadb` from Docker Hub | `13.0.2` | `MARIADB_VERSION` |
| [sqlmate](https://github.com/vdmitriyev/sqlmate) (shared, optional) | `sqlmate`, already on the server or built from the source in `SQLMATE_SOURCE` | `1.9.0` | `SQLMATE_VERSION` |
| [SurveyLite](https://github.com/vdmitriyev/surveylite) (shared, optional) | `surveylite`, already on the server or built from the source in `SURVEYLITE_SOURCE` | `0.21.0` (or newer) | `SURVEYLITE_VERSION` |

JupyterHub, NiFi and Superset are deprecated: the app creates no new accounts in them.

## Quick start

Requires Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and [Task](https://taskfile.dev/).

```bash
uv venv .venv
source .venv/bin/activate   # Windows: call .venv\Scripts\activate.bat
task setup                  # dependencies, env files in envs/ and setup/, database
task app:serve              # app on http://127.0.0.1:5353
```

Before `task app:serve`, change the secrets in `envs/webapp-dev-local.env`. See [docs/development.md](docs/development.md#configure).

## Tasks

The project uses [Task](https://taskfile.dev/). `task` lists all tasks. The main groups:

| Group | Main tasks | Guide |
| --- | --- | --- |
| `app:` | `app:serve`, `app:test`, `app:config`, `app:cli -- <command>` | [development](docs/development.md) |
| `dev:` | `dev:up`, `dev:init`, `dev:logs`, `dev:down`, `dev:app-recreate`, `dev:nginx-recreate` (Docker for development) | [development](docs/development.md#run-in-docker-for-development) |
| `prod:` | `prod:up`, `prod:down`, `prod:logs`, `prod:migrate`, `prod:app-recreate` (build the app again and recreate only its container) | [deployment](docs/deployment.md#production) |
| `prod:` nginx | `prod:cert -- <host>`, `prod:cert-renew`, `prod:nginx-reload` (check and reload the config), `prod:nginx-recreate` (build nginx again and recreate only its container) | [deployment](docs/deployment.md#https-certificate-lets-encrypt) |
| `sqlmate:` | `sqlmate:up`, `sqlmate:init`, `sqlmate:logs`, `sqlmate:down` | [deployment](docs/deployment.md#sqlmate-optional) |
| `surveylite:` | `surveylite:up`, `surveylite:logs`, `surveylite:down` | [deployment](docs/deployment.md#surveylite-optional) |
| `services:` | `services:versions`, `services:update-all`, `services:build-sqlmate`, `services:build-surveylite` | [deployment](docs/deployment.md#versions-of-the-services) |
| `testenv:` | `testenv:deploy`, `testenv:down` (Docker test copy) | [development](docs/development.md#tests) |

After `prod:app-recreate` or `dev:app-recreate`, the app needs a few seconds to start. Until then, nginx answers with 502. No migration task is needed: the app applies the migrations on each start.

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
