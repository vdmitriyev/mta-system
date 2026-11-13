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
task prod:nginx-reload                 # check the nginx configuration and reload it
task prod:nginx-recreate               # build nginx again and recreate only its container
task prod:app-recreate                 # build the app again and recreate only its container
```

`task prod:up` starts the app, nginx, PostgreSQL (port `5432` on all interfaces) and pgAdmin 4 (at `https://<SERVER_FQDN>/pgadmin4/`). PostgreSQL and pgAdmin 4 restart with the server.

| Task | What it does |
| --- | --- |
| `task prod:up` | Builds the images and starts all production containers |
| `task prod:down` | Stops and removes the production containers (the volumes stay) |
| `task prod:restart`, `task prod:ps` | Restarts the containers, shows their state |
| `task prod:logs -- <service>` | Shows the logs as they come in (all services without `-- <service>`) |
| `task prod:build` | Builds the images of the app and nginx without starting them |
| `task prod:migrate` | Applies the migrations to the database of the app |
| `task prod:cert -- <host>` | Gets a Let's Encrypt certificate for the host |
| `task prod:cert-renew` | Renews the certificates and reloads nginx |
| `task prod:nginx-reload` | Checks the nginx configuration and reloads it. Use it after a new certificate or after `task app:nginx-config`. The old name `prod:reload` still works. |
| `task prod:app-recreate` | Builds the app image again and recreates only the app container, for example after an update of the code. nginx, PostgreSQL and pgAdmin 4 keep running. At the end, it reloads nginx, so nginx finds the new container. The app then needs a few seconds to start: until then, nginx answers with 502. `prod:migrate` is not needed, because the app applies the migrations on each start. |
| `task prod:nginx-recreate` | Builds the nginx image again and recreates only the nginx container. The app and the databases keep running. Use it after a change in `provision/nginx/nginx-docker.conf`: this file is part of the image, so a reload does not read it. |

Before you go live:

1. Set `TARGET_SERVER=production`. This switches off the debug pages and the API docs, and makes the session cookie HTTPS-only.
2. Use new random values for `SECRET_KEY`, `HASH_KEY_LINKS` and `HASH_KEY_HIDDEN`, and for all passwords in `envs/`.
3. Set `SERVER_FQDN`, `SYSTEM_ADMINS`, `ALLOWED_FQDN_FOR_EMAILS` and the `MAIL_*` settings.
4. Keep the app behind nginx. Only nginx (`80`, `443`) and PostgreSQL (`5432`, or `POSTGRESQL_PUBLIC_PORT`) publish ports to all interfaces. All other ports are bound to `127.0.0.1`. Users log in to PostgreSQL with a password: use a strong `POSTGRES_PASSWORD` in `envs/postgresql-service.env`, and open the port in the firewall only for the networks that need it.
5. Back up the folder `data/` (SQLite database) and `.htpasswd_nginx/`.

### HTTPS certificate (Let's Encrypt)

nginx starts with a self-signed certificate. To get a certificate from Let's Encrypt:

1. The DNS entry of your host points to the server, and port `80` is open in the firewall. Let's Encrypt downloads a file from `http://<host>/.well-known/acme-challenge/` to check the host.
2. `task prod:up`, then `task prod:cert -- mtas.example.org`. certbot puts the file into `certbot/www`, nginx serves it from there, and certbot stores the certificate in `certbot/conf`.
3. In `provision/nginx/nginx-docker.conf`, use the two `ssl_certificate` lines with your host instead of the self-signed certificate.
4. `task prod:nginx-recreate`: this builds the nginx image with the changed file and recreates only the nginx container.
5. Renew the certificate before it expires (after 90 days): `task prod:cert-renew`, for example once a week with cron. It reloads nginx with `task prod:nginx-reload`.

nginx redirects all other requests on port `80` to HTTPS.

### Containers of the users

The app starts one Metabase and one OpenRefine container for each user. Their images must be on the server: `task services:pull-metabase` and `task services:build-openrefine`. Run them once, and again after a change in `versions.env`.

### Delete a user

On the admin page **Users**, **Delete** removes a user from the course:

* The user is marked as deleted and can no longer log in. The row stays in the database.
* The e-mail gets the prefix `deleted-<date>-<4 random characters>-`, for example `deleted-20261113-a1b2-sam@uni.example`. The address can then register again and gets a new account.
* The containers of the user (Metabase, OpenRefine, ...) are stopped, but not removed. The database of the user in PostgreSQL and the accounts in the other services stay.
* Admins cannot delete their own account.

### Optional services

| Service | How it starts | Details |
| --- | --- | --- |
| sqlmate | own compose file: `task sqlmate:up` | [sqlmate](#sqlmate-optional) |
| SurveyLite | own compose file: `task surveylite:up` | [SurveyLite](#surveylite-optional) |
| shared Metabase container | with `task prod:up`, if `metabase` is in `COMPOSE_PROFILES` | not needed: the app starts one for each user |
| shared OpenRefine container | with `task prod:up`, if `openrefine` is in `COMPOSE_PROFILES` | not needed: the app starts one for each user |

`COMPOSE_PROFILES` goes into the file `.env` in the project folder (not in git), for example `COMPOSE_PROFILES=metabase`. All `task` commands and docker compose read it.

## sqlmate (optional)

[sqlmate](https://github.com/vdmitriyev/sqlmate) gives SQL exercises to the students. It runs next to mta-system with its own compose file, `provision/sqlmate/compose.yml`, like SurveyLite and WordPress in `provision/`. It uses the image `sqlmate:<SQLMATE_VERSION>` on the server and its own settings in `envs/sqlmate-service.env`. `task prod:up` does not start it.

1. The image `sqlmate:<SQLMATE_VERSION>` (see `versions.env`) must be on the server. Check with `docker image ls sqlmate`. Without it, build it from the source in `SQLMATE_SOURCE`: `task services:build-sqlmate`.
2. `task app:init-env` copies `samples/sqlmate-service.env` to `envs/`. Change every `<CHANGE-ME>`. `SERVER_FQDN` of sqlmate is the one of the app.
3. In the env file of the app, set `SQLMATE_API_KEY` to the value of `API_KEY` in `envs/sqlmate-service.env` (starts with `smk_`, the sample shows how to make one). `SQLMATE_API_URL` and `SQLMATE_URL` work with their defaults.
4. Exercises: `setup/sqlmate/sql-exercises.yaml` and its files (see the README of sqlmate). `task app:init-env` puts a demo exercise there.
5. Start mta-system first (`task prod:up`). sqlmate joins its network, so nginx (`https://<SERVER_FQDN>/sqlmate/`) and the app reach it by its name. sqlmate publishes no port.
6. Start sqlmate:

   ```bash
   task sqlmate:up      # sqlmate and its database
   task sqlmate:init    # once: tables, sandbox database, API_KEY, exercises
   task sqlmate:logs
   ```

   Run `task sqlmate:init` again after an update of sqlmate (database migrations).
7. Switch on sqlmate on the page **Services → Auto creation**.

| Setting (shell or `.env`) | Default | Meaning |
| --- | --- | --- |
| `SQLMATE_NETWORK` | `mta-system-prod_mtas-network` | Network of mta-system. For development: `mta-system_mtas-network`. |
| `SQLMATE_DB_VOLUME` | `mta-system-prod_sqlmate-pgdata` | Volume of the sqlmate database. It is the volume of the earlier setup in `compose.services.yml`, so the data stays. |

Other tasks: `task sqlmate:ps`, `task sqlmate:restart`, `task sqlmate:down` (the data stays).

If sqlmate ran before as part of `task prod:up` (profile `sqlmate`, up to version 2.4.0), remove its old containers once before `task sqlmate:up`. The data stays in the volume: `docker rm -f mta-system-prod-sqlmate-service-1 mta-system-prod-sqlmate-database-1`.

## SurveyLite (optional)

[SurveyLite](https://github.com/vdmitriyev/surveylite) (version 0.21.0 or newer) runs anonymous surveys. It runs next to mta-system with its own compose file, `provision/surveylite/compose.yml`. It uses the image `surveylite:<SURVEYLITE_VERSION>` on the server and its own settings in `envs/surveylite-service.env`. `task prod:up` does not start it.

1. The image `surveylite:<SURVEYLITE_VERSION>` (see `versions.env`) must be on the server. Check with `docker image ls surveylite`. Without it, build it from the source in `SURVEYLITE_SOURCE`: `task services:build-surveylite`. The Dockerfile of SurveyLite needs BuildKit (`docker buildx`), which recent Docker versions include.
2. `task app:init-env` copies `samples/surveylite-service.env` to `envs/`. Change every `<CHANGE-ME>`. Set `SURVEYLITE_BASE_URL=https://<SERVER_FQDN>`.
3. In the env file of the app, set `SURVEYLITE_API_KEY` to one of `SURVEYLITE_API_KEYS` in `envs/surveylite-service.env`. `SURVEYLITE_API_URL` and `SURVEYLITE_URL` work with their defaults.
4. Surveys: YAML files in `setup/surveylite` (imported at each start), or build them in the admin pages of SurveyLite (`https://<SERVER_FQDN>/surveylite/admin`).
5. Start mta-system first (`task prod:up`). SurveyLite joins its network, so nginx and the app reach it by its name. It runs at `https://<SERVER_FQDN>/surveylite/` (`SURVEYLITE_URL_PREFIX=/surveylite` in the compose file, `location /surveylite/` in nginx). No DNS entry or certificate of its own is needed, and SurveyLite publishes no port.
6. Start SurveyLite:

   ```bash
   task surveylite:up
   task surveylite:logs
   ```

7. Switch on SurveyLite on the page **Services → Auto creation**.

| Setting (shell or `.env`) | Default | Meaning |
| --- | --- | --- |
| `SURVEYLITE_NETWORK` | `mta-system-prod_mtas-network` | Network of mta-system. For development: `mta-system_mtas-network`. |
| `SURVEYLITE_DATA_VOLUME` | `mta-system-prod_surveylite-data` | Volume of the SurveyLite data. It is the volume of the earlier setup in `compose.services.yml`, so the data stays. |

Other tasks: `task surveylite:ps`, `task surveylite:restart`, `task surveylite:down` (the data stays).

If SurveyLite ran before as part of `task prod:up` (profile `surveylite`, up to version 2.4.0), remove its old container once before `task surveylite:up`. The data stays in the volume: `docker rm -f mta-system-prod-surveylite-service-1`.

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
