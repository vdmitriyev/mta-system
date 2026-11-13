=======
History
=======

2.4.2 (2026-11-13)
-------------------

* New task `prod:app-recreate`: builds the app image again and recreates only the app container. nginx, PostgreSQL and pgAdmin 4 keep running. At the end, it reloads nginx, so nginx finds the new container (it looks up the address of the app only at start or reload). The app then needs a few seconds to start (migrations, exercises, workers). Until then, nginx answers with 502. `prod:migrate` is not needed: the app applies the migrations on each start.
* New tasks for development, like the ones of production: `dev:app-recreate`, `dev:nginx-recreate` and `dev:nginx-reload`.
* Docs: the README, `docs/deployment.md` and `docs/development.md` list the new tasks and say when to use them. The README, `docs/deployment.md` and `docs/development.md` also say that the app needs a few seconds to start after `prod:app-recreate` or `dev:app-recreate`, and that no migration task is needed.

2.4.1 (2026-11-13)
-------------------

* Admins can delete a user on the page **Users**. The user is not removed from the database, but marked as deleted and can no longer log in. The e-mail gets the prefix `deleted-<date>-<4 random characters>-`, for example `deleted-20261113-a1b2-sam@uni.example`, so the address can register again as a new user. Its containers (Metabase, OpenRefine, WordPress, ...) are stopped, but not removed. The databases and accounts of the user in the services stay. Admins cannot delete their own account.
* sqlmate runs with its own compose file `provision/sqlmate/compose.yml` (like WordPress), not in `compose.services.yml`. It uses the image `sqlmate:<SQLMATE_VERSION>` on the server and its settings in `envs/sqlmate-service.env`, joins the network of mta-system (`SQLMATE_NETWORK`) and keeps the database volume of before (`SQLMATE_DB_VOLUME`). New tasks `sqlmate:up`, `sqlmate:down`, `sqlmate:restart`, `sqlmate:ps`, `sqlmate:logs` and `sqlmate:init` (before: `prod:sqlmate-init`). `services:update-all` no longer builds sqlmate.
* SurveyLite also runs with its own compose file `provision/surveylite/compose.yml`, not in `compose.services.yml`. It uses the image `surveylite:<SURVEYLITE_VERSION>` on the server and its settings in `envs/surveylite-service.env`, joins the network of mta-system (`SURVEYLITE_NETWORK`) and keeps the data volume of before (`SURVEYLITE_DATA_VOLUME`). New tasks `surveylite:up`, `surveylite:down`, `surveylite:restart`, `surveylite:ps` and `surveylite:logs`. The profile `surveylite` is gone, and `services:update-all` no longer builds SurveyLite.
* Renamed `provision/wordpress/docker-compose.yml` to `provision/wordpress/compose.yml`.
* nginx: fixed `task prod:cert`. Port `80` answered all requests with 404, also the challenge files of Let's Encrypt (`/.well-known/acme-challenge/`), because a `return` at server level runs before the locations. Now nginx serves the challenge files and redirects all other requests to HTTPS. `docs/deployment.md` describes the steps for the certificate.
* New task `prod:nginx-recreate`: builds the nginx image again and recreates only the nginx container, for example after a change in `provision/nginx`. `prod:reload` is now `prod:nginx-reload`; the old name still works.
* nginx: fixed pgAdmin 4 at `/pgadmin4/`, which failed with 502 after pgAdmin was created again (new address). nginx now looks up the address at each request and also starts without pgAdmin. It passes HTTPS and the port of the user on to pgAdmin, and `/pgadmin4` goes to `/pgadmin4/`.
* SurveyLite: the login link and the survey links use the public address of SurveyLite (`SURVEYLITE_URL`). Before, a link without the prefix `/surveylite` (`https://<host>/me?auth=...`) opened the page `/me` of mta-system instead of SurveyLite.
* Dataset import into PostgreSQL: if a file is missing, the user sees only its name ("file not found: tutorial_flights.zip"), not its path on the server.
* Shorter descriptions of all tasks in `task --list`: what the task does, plus a usage hint where a task needs input. All start with a lowercase verb.
* Docs: the README lists the main task groups (new section **Tasks**). `docs/deployment.md` has a table of all `prod:` tasks and the section **Delete a user**. `docs/development.md` explains how to register again with the same address and how to rebuild nginx after a change of its config.

2.4.0 (2026-11-12)
-------------------

* New services **sqlmate** (SQL exercises) and **SurveyLite** (anonymous surveys) in `compose.services.yml`, built from their source folders (`SQLMATE_SOURCE`, `SURVEYLITE_SOURCE` in `versions.env`). The app creates the accounts through their APIs. The services page shows the login link, the login and the PIN of sqlmate, and the link to `/me`, the login, the PIN and the personal survey links of SurveyLite.
* SurveyLite participants are anonymous: only the new table `surveylite_service` of the app links a participant to a user.
* New admin pages **Services → sqlmate** and **Services → SurveyLite**: give surveys to the users, read their status, and choose services that open only after a completed survey.
* nginx: sqlmate at `/sqlmate/`, SurveyLite at `/surveylite/` (`SURVEYLITE_URL_PREFIX`). New task `prod:sqlmate-init`.
* sqlmate 1.9.0: the API key of the app is `API_KEY` in `envs/sqlmate-service.env` (same value as `SQLMATE_API_KEY` of the app); sqlmate stores it at start, so `flask api-create-key` is no longer needed. compose no longer mounts the `migrations` folder of the source, and sqlmate also starts without exercises.
* SurveyLite 0.21.0: the services page shows the personal login link of `/me` ("Log in to SurveyLite"), and the survey links also log the user in, so surveys with `require_login` open with one click. The admin page makes a new login link on request ("New login link"). Participants from before get their login link on the next visit of the services page. SurveyLite trusts the forwarded address of nginx (`FORWARDED_ALLOW_IPS`), so its login limits count per user address.
* The test copy also runs sqlmate, SurveyLite and the nginx of production, and checks them.
* sqlmate and SurveyLite are optional: Docker starts them only with their Compose profile (`COMPOSE_PROFILES=sqlmate,surveylite` in the file `.env` of the project folder). Without it, `task prod:up` and `task dev:up` need no source code of them. `services:update-all` builds them only if their profile is on, `prod:sqlmate-init` stops with a message if it is off, and `services:versions` shows `COMPOSE_PROFILES`.
* `task prod:up` and `task dev:up` no longer start the shared Metabase and OpenRefine containers (the app starts one of each for each user). They start only with the profiles `metabase` and `openrefine`. The OpenRefine image comes from `task services:build-openrefine`.
* `samples/webapp.env`: separate blocks for the settings of sqlmate and of SurveyLite.
* Production: PostgreSQL is reachable from outside (port `5432` on all interfaces, other port with `POSTGRESQL_PUBLIC_PORT`). PostgreSQL and pgAdmin 4 restart with the server (`restart: unless-stopped`). In development, PostgreSQL stays on `127.0.0.1`.
* The README is shorter: the setup, tests and API moved to `docs/development.md`, the Docker image, production and the versions of the services to `docs/deployment.md`. The README lists the supported versions of the services in a table.

2.3.0 (2026-11-11)
-------------------

* Deprecated JupyterHub, NiFi and Superset: the app creates no new accounts in them, also if they were switched on before. "Auto creation" and "Visibility" mark them, the command `auto-creation --on` refuses them.
* New settings `CONTAINER_NAME_PREFIX` (in front of the names of the containers and volumes of the users), `CONTAINER_PUBLISH_PORTS` (false: the containers are reached by their names only) and `WORDPRESS_DB_HOST` (MariaDB as the WordPress containers reach it).
* The test copy also runs pgAdmin 4, MariaDB and the containers of a user (Metabase, OpenRefine, WordPress), in two network variants, and checks each service.
* `task testenv:deploy` removes the test copy after the checks, also when a check fails (then it shows the logs first). `TESTENV_KEEP=true` keeps it running.
* Visibility: the columns key, description, status and action line up over all blocks.
* The addresses of the CSS and JavaScript files change with the files, so browsers load a changed file at once (before: only with a new version).
* About: the versions of the services come from `versions.env` (before: fixed in the page, partly old). Deprecated services show no version. New cards for MariaDB and WordPress, with their logos. "Jupyter Notebook (JupyterHub)" is now "JupyterHub".
* The theme button shows a sun or a moon icon instead of the text "Light theme" or "Dark theme".
* Fixed the space above and below the content of all pages (it was 0, so the About page touched the footer). The welcome text and the cards on the start page are centred.
* Header menu: the entries stay in one line. Below 960px the menu is behind the button "Menu" (before: 760px), up to 1200px the e-mail address is in the title of "Log out".
* Settings: the values are blue, empty values show "–".

2.2.0 (2026-11-11)
-------------------

* New file `versions.env` with the versions of all service images: Metabase, OpenRefine, WordPress (and its installer), PostgreSQL, pgAdmin 4 and MariaDB. The app, all `task` commands and the compose files read it. The page "Auto creation" shows the images. The PostgreSQL page compares the server version with it.
* New tasks `services:*` that show, pull or build the images. `services:update-all` gets all of them.
* OpenRefine Dockerfile: fixed the download address, which mixed 3.9.5 and 3.10.1 (404). Removed `provision/openrefine/build.sh`.
* The test copy uses the PostgreSQL version of `versions.env` (before: 15.8).
* MariaDB is pinned to 13.0.2 (before: `latest`, which was 13.0.2).
* Renamed the admin pages "Configuration" to "Settings" and "Service accounts" to "Auto creation". The old addresses forward. The command `service-accounts` is now `auto-creation`.
* Auto creation: separate columns for the service, how it runs, the version and a note.
* Visibility: the settings are grouped by category and service.

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
