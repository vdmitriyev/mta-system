=======
History
=======

2.1.0 (2026-11-11)
-------------------

* New admin page **PostgreSQL** (menu Services). It shows if the database server is reachable (address and version) and if the demo database exists. For each user it shows the database, the login and whether the database is on the server.
  * "Check access" logs in as each user into the own database: OK, LOGIN FAILED, NO DATABASE or DOWN.
  * "Create" sets up a missing database (with the stored login, if there is one).
  * "Set password" sets the password in PostgreSQL to the one that the user sees on the services page.
* New admin page **pgAdmin 4** (menu Services). It shows the login file of nginx and, for each user, whether the login with the stored password is in it.
  * "Check access" requests pgAdmin 4 with the login of each user.
  * "Write login" puts the login into the file again. "Create" sets up pgAdmin 4 for a user without an account.
* The databases and users in PostgreSQL are set up with the package `dbsetupmate` (0.8.1) instead of own SQL. Errors are reported with a clear text, for example "database already exists".
* The number of a new database is the highest number in use plus one (before: the number of databases plus one). Deleted databases no longer cause a collision.
* A new database of a user counts as created even if the demo database is missing. The missing access to the demo database is written to the log.
* Services page of the users: one service per row, over the full width.

2.0.0 (2026-11-10)
-------------------

* Rewrote the web app with FastAPI (served by uvicorn). Removed Flask, Flask-Login, Flask-SQLAlchemy, Flask-Migrate and gunicorn.
* Removed Redis and RQ. Long-running jobs (registration, dataset import, setup of containers, prepared accounts) run as background tasks of FastAPI. Their state is stored in the new table `background_tasks`.
* Added the JSON API `/api/health`, `/api/tasks/{id}` and `/api/services/status`.
* Added the setting `ENABLE_API_DOCS`. The FastAPI docs are off in production by default.
* New UI with one stylesheet and one script of the app. No files from a CDN.
* Forms that change data use POST with a CSRF token. Messages are shown once and no longer come from the address of the page.
* Replaced the `flask` commands with `python -m app.cli <command>`. Migrations use Alembic directly.
* Added tests for the app (`task app:test`, `task app:coverage`) and an end-to-end check for the Docker test copy.
* Added sample env files and exercises in `samples/` (`task app:init-env`).
* Removed dead code: test pages, unused templates, commented code, the broken "generate bash commands" admin actions, unused helper functions and command line blocks of the service modules.
* Renamed `FLASK_SECRET_KEY` to `SECRET_KEY` (the old name still works).
* The settings use `pydantic-settings`. Wrong values (for example `MAIL_PORT=abc` or `CREATE_METABASE_SERVICE=maybe`) stop the start with a message that names the variable. Passwords and keys are hidden in logs and on the admin pages.
* Environment variables now win over the values in the env file (before: the env file won).
* Lists (`ALLOWED_FQDN_FOR_EMAILS`, `SYSTEM_ADMINS`, `SERVICES_UI`) can be separated by `;` or `,`, also as `['a', 'b']`. E-mail domains and admin addresses are compared without case.
* If the SMTP server cannot be reached, the log shows one line with the server, the port and what to check, not a traceback. Added the setting `MAIL_TIMEOUT_SEC` (default: 10 seconds, before: 30) and the command `check-mail`.
* Moved the settings `CREATE_<NAME>_SERVICE` from the env file into the database (table `service_settings`). Admins change them on the new page **Admin → Service accounts** or with `python -m app.cli service-accounts`. The migration copies the old values once.
* The pages use the full width of the window. More space above the admin menu.
* Dark mode: the button in the header switches between the light and the dark theme. The choice is stored in the browser. Without a choice, the system setting decides.
* The font is a bit bigger on all pages (17 px instead of 16 px).
* Admin menu: the new drop-down menu "Services" holds Metabase, OpenRefine and Service accounts. The access check (basic auth) moved to the OpenRefine page (button "Check access"). The old address forwards to it.
* Configuration page: the names and ports of the accounts (`*_PREFIX`, `*_OFFSET`) are shown in the block of their service.
* Background tasks no longer wait forever. A task fails when the worker process that runs it is gone (restart, crash) or when it runs for more than 30 minutes (before: 2 hours). The page stops waiting after 15 minutes or when the server does not know the task. New column `background_tasks.worker_pid`.
* Before a Metabase or OpenRefine container is created, the app checks that the image (name and version) is on the server or in the registry. If not, nothing is changed: "Create again" keeps the old container. The admin page of the service shows the state of the image and, if it is missing, the command that gets it.
* Added the command `show-config` and the tasks `setup`, `app:start`, `app:cli`, `app:config` and `dev:*` (development in Docker with `compose.yml` and `compose.services.yml`).

1.3.0 (2026-11-10)
-------------------

* Moved the env files to the folder `envs/`.
* Excluded `envs/` from git (`.gitignore`) and the Docker image (`.dockerignore`).
* Updated the env file paths in `compose.services.yml`, `compose.prod.yaml` (default: `envs/.env`) and `tests/testenv/compose.yaml`.
* Changed the default `ENV_FILE_NAME` to `envs/webapp-dev-local.env` in `Taskfile.yaml` and `helpers.py`.
* Updated the env file path of the test copy in `taskfiles/Taskfile_testenv.yaml`.
* Described the folder `envs/` in `README.md`.

1.2.0 (2026-11-08)
-------------------

* Migrating code from the other repository to this - this bring a lot of new features into the application

1.2.0 (2026-03-22)
-------------------

* Added citation details for the modular teaching assistance system.
* Added BibTeX citation section to `README.md`.

1.1.0 (2024-03-07)
-------------------

* Added virtual environment creation scripts.
* Configured initial documentation suite using Sphinx.
* Fixed minor typo in `README.md`.

1.0.0 (2021-05-16)
-------------------

* Initial release of `mta-system`.
* Added core application code for the `mta-system` Flask webserver, static files, and HTML templates.
* Added data importer module along with initial datasets.
* Added deployment requirements files, production startup scripts, and `.env` setup scripts with documentation.
* Integrated logging configurations and removed debug print statements.
* Added administrative feature to manage JupyterHub users via the web UI.
* Fixed registration handling for invalid configuration inputs.
* Fixed server metrics display to function when Docker is not running.
* Initialized system documentation and added `README.md`.
