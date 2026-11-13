# Deployment

How to run the app with Docker on a server. For the setup on your computer, see [development.md](development.md).

## Docker image

```bash
task app:build-image   # builds mta-system:latest
```

* On start, the container applies the migrations and imports the exercises. Then it runs uvicorn on port `5151`.
* `WEB_CONCURRENCY` sets the number of worker processes (default: 4).
* Mount `/mta-system/data` (SQLite database) and `/mta-system/.logs` as volumes.
* To start and stop the service containers, the app needs `/var/run/docker.sock`.

## Production

```bash
cp samples/webapp.env envs/.env        # then set TARGET_SERVER=production and your values
task prod:up                           # app, nginx, PostgreSQL and pgAdmin 4
task prod:cert -- mtas.example.org     # Let's Encrypt certificate
task prod:logs
```

`task prod:up` starts the app, nginx, PostgreSQL (port `5432` on all interfaces) and pgAdmin 4 (at `https://<SERVER_FQDN>/pgadmin4/`). PostgreSQL and pgAdmin 4 restart with the server. It does not start the shared Metabase and OpenRefine containers: the app starts one container of each for each user. If you still want them, add `metabase` or `openrefine` to `COMPOSE_PROFILES` (see below). `task prod:up` also no longer builds the OpenRefine image: run `task services:build-openrefine` once, and after a change of `OPENREFINE_VERSION`.

Before you go live:

1. Set `TARGET_SERVER=production`. This switches off the debug pages and the API docs, and makes the session cookie HTTPS-only.
2. Use new random values for `SECRET_KEY`, `HASH_KEY_LINKS` and `HASH_KEY_HIDDEN`, and for all passwords in `envs/`.
3. Set `SERVER_FQDN`, `SYSTEM_ADMINS`, `ALLOWED_FQDN_FOR_EMAILS` and the `MAIL_*` settings.
4. Keep the app behind nginx. Only nginx (`80`, `443`) and PostgreSQL (`5432`, or `POSTGRESQL_PUBLIC_PORT`) publish ports to all interfaces. All other ports are bound to `127.0.0.1`. Users log in to PostgreSQL with a password: use a strong `POSTGRES_PASSWORD` in `envs/postgresql-service.env`, and open the port in the firewall only for the networks that need it.
5. Back up the folder `data/` (SQLite database) and `.htpasswd_nginx/`.

### sqlmate in production (optional)

sqlmate runs next to mta-system with its own compose file, `provision/sqlmate/compose.yml`, like WordPress in `provision/wordpress`. It uses the image `sqlmate:<SQLMATE_VERSION>` that is already on the server, and its own settings in `envs/sqlmate-service.env`. `task prod:up` does not start it.

1. The image `sqlmate:<SQLMATE_VERSION>` (see `versions.env`) must be on the server. Check with `docker image ls sqlmate`. Without it, build it from the source in `SQLMATE_SOURCE`: `task services:build-sqlmate`.
2. `task app:init-env` copies `samples/sqlmate-service.env` to `envs/`. Change every `<CHANGE-ME>`. `SERVER_FQDN` of sqlmate is the one of the app. `API_KEY` of sqlmate (starts with `smk_`, the sample shows how to make one) goes into the env file of the app as `SQLMATE_API_KEY`.
3. Exercises: `setup/sqlmate/sql-exercises.yaml` and its files (see the README of sqlmate). `task app:init-env` puts a demo exercise there.
4. Start mta-system first (`task prod:up`): sqlmate joins its network `mta-system-prod_mtas-network`, so nginx (`https://<SERVER_FQDN>/sqlmate/`) and the app reach it by its name. sqlmate publishes no port.
5. Start sqlmate:

   ```bash
   task sqlmate:up      # sqlmate and its database
   task sqlmate:init    # once: tables, sandbox database, API_KEY, exercises
   task sqlmate:logs
   ```

   Run `task sqlmate:init` again after an update of sqlmate (database migrations).
6. Switch on sqlmate on the page **Services → Auto creation**.

| Setting (shell or `.env`) | Default | Meaning |
| --- | --- | --- |
| `SQLMATE_NETWORK` | `mta-system-prod_mtas-network` | Network of mta-system. For development: `mta-system_mtas-network`. |
| `SQLMATE_DB_VOLUME` | `mta-system-prod_sqlmate-pgdata` | Volume of the sqlmate database. It is the volume of the earlier setup in `compose.services.yml`, so the data stays. |

If sqlmate ran before as part of `task prod:up` (profile `sqlmate`), remove its old containers once before `task sqlmate:up`. The data stays in the volume: `docker rm -f mta-system-prod-sqlmate-service-1 mta-system-prod-sqlmate-database-1`.

### SurveyLite in production (optional)

SurveyLite is optional. By default, `task prod:up` does not start it and does not need its source code. To use it:

1. Switch it on with a Compose profile. Put this line into the file `.env` in the project folder (not in git):

   ```ini
   COMPOSE_PROFILES=surveylite
   ```

   All `task prod:*` and `task services:*` commands read it. Without the line, the steps below are not needed.
2. Put the source code of SurveyLite into the folder `SURVEYLITE_SOURCE` of `versions.env` (default: `temp/surveylite`). compose builds the image from there. The Dockerfile of SurveyLite needs BuildKit (`docker buildx`), which recent Docker versions include.
3. `task app:init-env` copies `samples/surveylite-service.env` to `envs/`. Change every `<CHANGE-ME>`. One of `SURVEYLITE_API_KEYS` goes into the env file of the app as `SURVEYLITE_API_KEY`.
4. SurveyLite runs at `https://<SERVER_FQDN>/surveylite/` (`SURVEYLITE_URL_PREFIX=/surveylite` in `compose.services.yml`, `location /surveylite/` in nginx). Set `SURVEYLITE_BASE_URL=https://<SERVER_FQDN>` in `envs/surveylite-service.env`. No DNS entry or certificate of its own is needed.
5. Surveys: YAML files in `setup/surveylite`, or build them in the admin pages of SurveyLite (`https://<SERVER_FQDN>/surveylite/admin`).
6. Switch on SurveyLite on the page **Services → Auto creation**.

## Versions of the services

The versions of the service images are in one file, `versions.env` in the project folder. The [README](../README.md#supported-versions-of-the-services) lists them.

These read the same file:

| Who | How |
| --- | --- |
| the web app | as an env file with the lowest priority: a variable in the environment or in the env file of the app wins |
| all `task` commands | `dotenv` in `Taskfile.yaml`, e.g. for the docker compose calls |
| `compose.services.yml`, `tests/testenv/compose.yaml`, `provision/wordpress/compose.yml` | `task dev:up`, `task prod:up`, `task testenv:deploy`, or `docker compose --env-file versions.env ...`. Without the file, compose stops with a message. |

The admin page **Services → Auto creation** shows the versions, `task services:versions` too. The page **Services → PostgreSQL** compares the version that the server runs with `POSTGRESQL_VERSION`.

To change a version:

1. Change it in `versions.env`.
2. Get the image on the server: `task services:pull-metabase`, `task services:build-openrefine`, `task services:pull-wordpress`, `task services:pull-postgresql`, `task services:pull-pgadmin4`, `task services:pull-mariadb`, `task services:build-sqlmate` or `task services:build-surveylite`. `task services:update-all` gets all of them.
3. Restart the app. The admin page of the service shows if the image is on the server.
4. New users get the new version. For an existing user, use "Create again" on the admin page of the service. For PostgreSQL and pgAdmin 4, restart the service: `task prod:up`. For MariaDB, restart `provision/wordpress/compose.yml` with `--env-file versions.env`.

A new major version of PostgreSQL (for example 15 to 17) cannot open the data of the old one. Dump the databases before the change and restore them afterwards. MariaDB cannot go back to an older version once a newer one wrote the data.
