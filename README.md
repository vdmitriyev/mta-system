## About

**mta-system** (**m**odular **t**eaching **a**ssistance **system**) gives students hands-on experience with software. A lecturer hosts it for a course. Each student gets an own account in services such as PostgreSQL, pgAdmin 4, Metabase and OpenRefine. Optional: SQL exercises ([sqlmate](https://github.com/vdmitriyev/sqlmate)) and anonymous surveys ([SurveyLite](https://github.com/vdmitriyev/surveylite)).

* **Students** register with their e-mail address and a course code. They see the logins of their services, start their containers, import sample datasets, and read the reviews and bonus points of their exercises.
* **Admins** write reviews and bonus points. They manage the databases, logins and containers of the users, prepare accounts, delete users, choose the visible parts of the pages, and watch the server.

The pages have a light and a dark theme. The button in the header switches it.

Documentation: [vdmitriyev.github.io/mta-system](https://vdmitriyev.github.io/mta-system/)

| Guide | Content |
| --- | --- |
| [docs/development.md](docs/development.md) | Install, settings, run the app, Docker for development, commands, API, tests |
| [docs/deployment.md](docs/deployment.md) | Server, HTTPS certificate, pgAdmin 4 login, delete users, sqlmate, SurveyLite, versions of the services |
| [HISTORY.rst](HISTORY.rst) | Changes of each version. Read it before you update a server. |

## Architecture

| Part | Technology |
| --- | --- |
| Web app | [FastAPI](https://fastapi.tiangolo.com/) with Jinja2 templates and uvicorn |
| Data of the app | SQLite, migrations with Alembic |
| Long jobs | Background tasks of FastAPI, state in the table `background_tasks`. No Redis, no extra worker. |
| Services of the students | One Docker container per user for Metabase, OpenRefine and WordPress. Shared PostgreSQL (set up with [dbsetupmate](https://pypi.org/project/dbsetupmate/)), pgAdmin 4 and MariaDB. |
| Entry point in production | nginx: HTTPS and the logins of the containers and of pgAdmin 4 |

```
app/
  app.py            creates the FastAPI app
  config.py         settings from environment variables
  routers/          pages (public, account, admin) and the JSON API
  tasks.py          background tasks
  users.py          login data and registration
  provisioning.py   creates the accounts of a user in the services
  services/         PostgreSQL, MariaDB, Docker, Metabase, OpenRefine, ...
  importers/        sample datasets for the PostgreSQL database of a user
  cli/              commands: python -m app.cli <command>
  templates/        HTML pages
  static/           stylesheet, script, images (no CDN)
docs/               development and deployment guides
migrations/         Alembic migrations of the SQLite database
provision/          nginx, pgAdmin 4, OpenRefine, WordPress, sqlmate, SurveyLite
samples/            samples of the env files and the exercises
tests/              tests, tests/testenv/ is the Docker test copy
```

Registration, dataset imports and new containers can take minutes. The app runs them as background tasks and answers at once. The page then shows the result. A task fails after 30 minutes or when its worker stops.

## Supported versions of the services

`versions.env` holds the versions. `task services:versions` shows them. To change one and get the new image, see [Versions of the services](docs/deployment.md#versions-of-the-services).

| Service | Image | Version | Variable |
| --- | --- | --- | --- |
| Metabase (per user) | `metabase/metabase` | `v0.57.3` | `METABASE_VERSION` |
| OpenRefine (per user) | `openrefine`, built from `provision/openrefine` | `3.10.1` | `OPENREFINE_VERSION` |
| WordPress (per user) | `wordpress` | `latest` | `WORDPRESS_VERSION` |
| WP-CLI (installs WordPress) | `wordpress` | `cli` | `WORDPRESS_CLI_VERSION` |
| PostgreSQL (shared) | `postgres` | `17.11` | `POSTGRESQL_VERSION` |
| pgAdmin 4 (shared) | `dpage/pgadmin4` | `9.19` | `PGADMIN4_VERSION` |
| MariaDB (shared, for WordPress) | `mariadb` | `13.0.2` | `MARIADB_VERSION` |
| sqlmate (shared, optional) | `sqlmate`, must be on the server | `1.9.0` | `SQLMATE_VERSION` |
| SurveyLite (shared, optional) | `surveylite`, must be on the server | `0.21.0` or newer | `SURVEYLITE_VERSION` |

The images come from Docker Hub, except OpenRefine, sqlmate and SurveyLite. `task services:build-sqlmate` and `task services:build-surveylite` build these two from `temp/sqlmate` and `temp/surveylite`. JupyterHub, NiFi and Superset are deprecated.

## Quick start

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and [Task](https://taskfile.dev/).

```bash
uv venv .venv
source .venv/bin/activate   # Windows: call .venv\Scripts\activate.bat
task setup                  # dependencies, env files, database
task app:serve              # app on http://127.0.0.1:5353
```

Before `task app:serve`, change the secrets in `envs/webapp-dev-local.env`. See [Configure](docs/development.md#configure). `task setup` also creates `envs/pgadmin4-proxy.env` from `samples/pgadmin4-proxy.env`. It holds the secret of nginx and pgAdmin 4.

## Tasks

`task` lists all tasks. The main groups:

| Group | Main tasks | Guide |
| --- | --- | --- |
| `app:` | `app:serve`, `app:test`, `app:config`, `app:init-env`, `app:cli -- <command>` | [development](docs/development.md) |
| `dev:` | `dev:up`, `dev:init`, `dev:logs`, `dev:down`, `dev:app-recreate`, `dev:nginx-recreate` | [development](docs/development.md#run-in-docker-for-development) |
| `prod:` | `prod:up`, `prod:down`, `prod:logs`, `prod:migrate`, `prod:app-recreate` | [deployment](docs/deployment.md#production) |
| `prod:` nginx | `prod:cert -- <host>`, `prod:cert-renew`, `prod:nginx-reload`, `prod:nginx-recreate` | [deployment](docs/deployment.md#https-certificate-lets-encrypt) |
| `sqlmate:` | `sqlmate:up`, `sqlmate:init`, `sqlmate:logs`, `sqlmate:down` | [deployment](docs/deployment.md#sqlmate-optional) |
| `surveylite:` | `surveylite:up`, `surveylite:logs`, `surveylite:down` | [deployment](docs/deployment.md#surveylite-optional) |
| `services:` | `services:versions`, `services:update-all`, `services:build-sqlmate`, `services:build-surveylite` | [deployment](docs/deployment.md#versions-of-the-services) |
| `testenv:` | `testenv:deploy`, `testenv:down` | [development](docs/development.md#tests) |

After `prod:app-recreate` or `dev:app-recreate`, the app needs a few seconds to start. Until then, nginx answers with 502. You do not need a migration task: the app applies the migrations on each start.

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

* Source code: MIT
* Datasets: see the license in each import module or dataset
