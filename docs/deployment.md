# Deployment

How to run mta-system with Docker on a server. For your computer, see [development.md](development.md). Before you update a server, read the changes in [HISTORY.rst](../HISTORY.rst).

## Docker image

```bash
task app:build-image   # builds mta-system:latest
```

* On start, the container applies the migrations and imports the exercises. Then it runs uvicorn on port `5151`.
* `WEB_CONCURRENCY` sets the number of workers (default: 4).
* Mount `/mta-system/data` (SQLite database) and `/mta-system/.logs` as volumes.
* The app needs `/var/run/docker.sock` to start and stop the containers of the users.

## Production

1. Copy the settings: `cp samples/webapp.env envs/.env`. Set `TARGET_SERVER=production` and your values.
2. Tell the tasks to use this file: `export ENV_FILE_NAME=envs/.env`. Put this line in `~/.profile` of the server user, so each shell has it.
3. Create the other env files: `task app:init-env`. It keeps existing files.
4. Start: `task prod:up`. This starts the app, nginx, PostgreSQL and pgAdmin 4.
5. Create the accounts of the admins: `task prod:create-admins`. See [Admin accounts](#admin-accounts).

Without `ENV_FILE_NAME`, all tasks use `envs/webapp-dev-local.env`, also the `prod:` tasks. The file `.env` in the project folder cannot set `ENV_FILE_NAME`. To check it: `echo $ENV_FILE_NAME`.

Before you go live:

1. Use new random values for `SECRET_KEY`, `HASH_KEY_LINKS`, `HASH_KEY_HIDDEN` and all passwords in `envs/`.
2. Set `SERVER_FQDN`, `SYSTEM_ADMINS`, `ALLOWED_FQDN_FOR_EMAILS` and `MAIL_*`.
3. Only nginx (`80`, `443`) and PostgreSQL (`5432`, or `POSTGRESQL_PUBLIC_PORT`) are open to all networks. Use a strong `POSTGRES_PASSWORD` in `envs/postgresql-service.env`. Open `5432` in the firewall only for the networks that need it.
4. Back up `.backups/` (see [Backup of the database](#backup-of-the-database)), `submissions/` and `.htpasswd_nginx/`.

`TARGET_SERVER=production` switches off the debug pages and the API docs. The session cookie then works only over HTTPS.

| Task | What it does |
| --- | --- |
| `task prod:up` | Builds the images and starts all containers. |
| `task prod:down` | Stops and removes the containers. The volumes stay. |
| `task prod:restart`, `task prod:ps` | Restarts the containers, shows their state. |
| `task prod:logs -- <service>` | Shows the logs. Without `-- <service>`: all services. |
| `task prod:build` | Builds the images of the app and nginx. |
| `task prod:migrate` | Applies the migrations to the database of the app. |
| `task prod:backup` | Copies the database of the app to `.backups/`. |
| `task prod:export-exercises` | Writes the exercises as CSV to `.backups/`. |
| `task prod:create-admins` | Creates the accounts of `SYSTEM_ADMINS`. Prints the login data and sends it by e-mail. |
| `task prod:cert` | Gets a Let's Encrypt certificate for `SERVER_FQDN` and restarts nginx. |
| `task prod:cert-renew` | Renews the certificates and reloads nginx. |
| `task prod:nginx-reload` | Checks the nginx configuration and reloads it. Old name: `prod:reload`. |
| `task prod:nginx-recreate` | Builds nginx again and recreates only nginx. Use it after a change in `provision/nginx/nginx-docker.conf`: the file is part of the image. |
| `task prod:app-recreate` | Builds the app again, recreates only the app and reloads nginx. |

After `task prod:app-recreate`, the app needs a few seconds to start. Until then, nginx answers with 502. You do not need `task prod:migrate`: the app applies the migrations on each start.

### HTTPS certificate (Let's Encrypt)

nginx starts with a self-signed certificate. To get one from Let's Encrypt:

1. Set `SERVER_FQDN` in the env file of the app, for example `SERVER_FQDN=mtas.example.org`.
2. Point the DNS entry of this host to the server. Open port `80` in the firewall.
3. Run `task prod:up`, then `task prod:cert`.
4. Renew the certificate before 90 days pass: `task prod:cert-renew`, for example weekly with cron.

`task prod:cert` reads `SERVER_FQDN` from the env file in `ENV_FILE_NAME` (see [Production](#production)).

You do not change `provision/nginx/nginx-docker.conf`. On each start, nginx uses the certificate in `certbot/conf/live/<SERVER_FQDN>/` if it exists. Else it uses the self-signed one.

Let's Encrypt checks the host at `http://<SERVER_FQDN>/.well-known/acme-challenge/`. nginx redirects all other requests on port `80` to HTTPS.

If you edited `nginx-docker.conf` on the server before:

1. Drop the local change: `git checkout provision/nginx/nginx-docker.conf`. Then run `git pull`.
2. Check that `SERVER_FQDN` is the name of the folder in `certbot/conf/live/`. Else get a new certificate with `task prod:cert`.
3. Run `task prod:nginx-recreate`.

### Containers of the users

The app starts one Metabase and one OpenRefine container for each user. Get their images once, and again after a change in `versions.env`:

```bash
task services:pull-metabase
task services:build-openrefine
```

### pgAdmin 4

pgAdmin 4 runs at `https://<SERVER_FQDN>/pgadmin4/`. nginx asks for the login of the user. nginx then sends the user name and a secret to pgAdmin. pgAdmin logs the user in.

* The secret is in `envs/pgadmin4-proxy.env`. `task app:init-env` creates it from `samples/pgadmin4-proxy.env` with a random value. nginx and pgAdmin read the same file.
* Without the secret, pgAdmin shows its own login page. So other containers in the network cannot log in as a user.
* `task prod:up` and `task prod:nginx-recreate` stop if the file is missing.
* To change the secret, edit the file and run `task prod:up`.
* pgAdmin listens on port `8080` (`PGADMIN_LISTEN_PORT` in `compose.services.yml`). Port `80` fails on servers where Docker uses `no-new-privileges`. nginx then answers with 502.
* If nginx answers with 502, read `.logs/nginx/error.log`. To test the connection from nginx: `docker exec mta-system-nginx ping -c 3 pgadmin4-service`.

`provision/pgadmin4/config_local.py` holds the settings:

| Setting | Meaning |
| --- | --- |
| `WEBSERVER_REMOTE_USER_FROM_HEADER = True` | Read the user name from the header `X-Forwarded-User`. |
| `WEBSERVER_TRUSTED_PROXIES` | Accept the header only from the private networks of Docker, where nginx runs. |
| `WEBSERVER_SHARED_SECRET` | Accept the header only with the secret (`X-Pgadmin-Webserver-Secret`). |

To update a server from pgAdmin 8.x (mta-system 2.4.2 or older):

1. Back up the volume `pga4volume-service`. pgAdmin 9.x changes the data in it on the first start.
2. Run `task app:init-env`.
3. Run `task services:pull-pgadmin4`, then `task prod:up`.
4. Log in at `/pgadmin4/` as a user. You must see the account of the user, not the login page of pgAdmin.

### Admin accounts

`task prod:create-admins` creates an account for each e-mail in `SYSTEM_ADMINS`:

* It prints the user ID, the PIN and the login link of each admin on the screen. The log file gets only the e-mail, not the link.
* It sends the login data by e-mail, if the mail server works. Without e-mail: `task prod:create-admins -- --no-mail`.
* An existing account stays. The task prints its login data again.

### Backup of the database

`task prod:backup` copies the SQLite database of the app to `.backups/`, for example `.backups/20261113-201500-mta-system.db`. The name starts with the date and time.

* The copy is complete also while the app runs.
* Git and the Docker image do not include `.backups/`.
* Copy the folder to another computer. For a daily backup, run the task with cron.

On your computer, `task db:backup` does the same.

### Submissions

Students upload their reports on the page **Submissions**: PDF, TXT, MD or DOCX files. Until the deadline they can upload more files and delete them. After the deadline the files stay, but the students cannot change them.

* The admin page **Exercises** switches the submissions of an exercise on, sets the deadline and switches the confirmation e-mail on or off. The e-mail lists the files with their size and SHA-256 hash.
* The admin page **Submissions** shows the number of files per user and exercise. A click on a cell lists the files (also the deleted ones), and sets or removes a personal deadline for this user. **ZIP** downloads all files of an exercise.
* The files are in `submissions/` on the host (`SUBMISSIONS_DIR` in the container): `<user-id>_<name>/<EXERCISE_CODE>/<file>`, for example `submissions/0007_sam.student/EX01/report.pdf`.
* One upload has at most 10 MB. The app checks it, and nginx rejects larger uploads (`client_max_body_size 11M` for `/submissions/<code>/upload`).
* The deadline is the local time of the server (`TZ` in `compose.prod.yaml`).
* `task prod:backup` does not copy `submissions/`. Back up this folder on its own.
* The page needs the menu entry **Submissions** on the admin page **Visibility** (on by default).

### Exercises as CSV

Changes on the admin page **Exercises** are stored in the database only. **Download CSV** on this page gives all exercises in the format of `setup/initial_exercises.csv`.

* Keep the file as a backup, or save it as `setup/initial_exercises.csv` for a new deployment.
* On the server: `task prod:export-exercises` writes the file to `.backups/<date>-<time>-initial_exercises.csv`.
* The import adds only exercises with a new code. It does not change existing exercises. Use the file for a new (empty) database.

### Login history

The admin page **Logins** (in the menu after **Monitoring**) lists the newest 200 login attempts: time, user ID, method and result. A click on a user ID shows only the logins of this user. The e-mail is not stored, only the user ID. The ID is the same as on the page **Users**.

### Delete a user

On the admin page **Users**, **Delete** removes a user from the course:

* The user can no longer log in. The row stays in the database.
* The e-mail gets a prefix, for example `deleted-20261113-a1b2-sam@uni.example`. The address can register again.
* The containers of the user stop. They are not removed. The databases and accounts of the user stay.
* Admins cannot delete their own account.

### Optional services

| Service | How to start it |
| --- | --- |
| sqlmate | `task sqlmate:up`, see [sqlmate](#sqlmate-optional) |
| SurveyLite | `task surveylite:up`, see [SurveyLite](#surveylite-optional) |
| shared Metabase | `task prod:up` with `metabase` in `COMPOSE_PROFILES`. Not needed: each user has a container. |
| shared OpenRefine | `task prod:up` with `openrefine` in `COMPOSE_PROFILES`. Not needed: each user has a container. |

Put `COMPOSE_PROFILES` in the file `.env` in the project folder, for example `COMPOSE_PROFILES=metabase`.

## sqlmate (optional)

[sqlmate](https://github.com/vdmitriyev/sqlmate) gives SQL exercises to the students. It has its own compose file (`provision/sqlmate/compose.yml`) and settings (`envs/sqlmate-service.env`).

1. Get the image `sqlmate:<SQLMATE_VERSION>` on the server. Check it with `docker image ls sqlmate`. To build it from the source in `temp/sqlmate`: `task services:build-sqlmate`.
2. In `envs/sqlmate-service.env`, change every `<CHANGE-ME>`. Use the `SERVER_FQDN` of the app.
3. In the env file of the app, set `SQLMATE_API_KEY` to `API_KEY` of `envs/sqlmate-service.env`.
4. Put the exercises in `setup/sqlmate/sql-exercises.yaml`. `task app:init-env` adds a demo exercise.
5. Start mta-system first, then sqlmate:

   ```bash
   task sqlmate:up      # sqlmate and its database
   task sqlmate:init    # once, and after each update of sqlmate
   ```

6. Switch on sqlmate on the admin page **Services → Auto creation**.

sqlmate runs at `https://<SERVER_FQDN>/sqlmate/`. It joins the network of mta-system and opens no port. Other tasks: `sqlmate:ps`, `sqlmate:logs`, `sqlmate:restart`, `sqlmate:rebuild` (builds the image again and replaces the running sqlmate), `sqlmate:down` (the data stays).

| Setting (shell or `.env`) | Default |
| --- | --- |
| `SQLMATE_NETWORK` | `mta-system-prod_mtas-network`. For development: `mta-system_mtas-network`. |
| `SQLMATE_DB_VOLUME` | `mta-system-prod_sqlmate-pgdata` |

Up to version 2.4.0, `task prod:up` started sqlmate. Remove the old containers once before `task sqlmate:up`. The data stays: `docker rm -f mta-system-prod-sqlmate-service-1 mta-system-prod-sqlmate-database-1`.

## SurveyLite (optional)

[SurveyLite](https://github.com/vdmitriyev/surveylite) (0.21.0 or newer) runs anonymous surveys. It has its own compose file (`provision/surveylite/compose.yml`) and settings (`envs/surveylite-service.env`).

1. Get the image `surveylite:<SURVEYLITE_VERSION>` on the server. Check it with `docker image ls surveylite`. To build it from the source in `temp/surveylite`: `task services:build-surveylite`. This needs `docker buildx`.
2. In `envs/surveylite-service.env`, change every `<CHANGE-ME>`. Set `SURVEYLITE_BASE_URL=https://<SERVER_FQDN>`, with `https://` and without `/surveylite`. SurveyLite adds `/surveylite` itself.
3. In the env file of the app, set `SURVEYLITE_API_KEY` to one of `SURVEYLITE_API_KEYS` of `envs/surveylite-service.env`.
4. Put the surveys in `setup/surveylite` as YAML files, or build them at `https://<SERVER_FQDN>/surveylite/admin`.
5. Start mta-system first, then SurveyLite: `task surveylite:up`.
6. Switch on SurveyLite on the admin page **Services → Auto creation**.

SurveyLite runs at `https://<SERVER_FQDN>/surveylite/`. If **Log in to SurveyLite** opens a wrong address, check `SURVEYLITE_BASE_URL`, then run `task surveylite:up` (a restart does not read the env file again). It joins the network of mta-system and opens no port. Other tasks: `surveylite:ps`, `surveylite:logs`, `surveylite:restart`, `surveylite:rebuild` (builds the image again and replaces the running SurveyLite), `surveylite:down` (the data stays).

| Setting (shell or `.env`) | Default |
| --- | --- |
| `SURVEYLITE_NETWORK` | `mta-system-prod_mtas-network`. For development: `mta-system_mtas-network`. |
| `SURVEYLITE_DATA_VOLUME` | `mta-system-prod_surveylite-data` |

Up to version 2.4.0, `task prod:up` started SurveyLite. Remove the old container once before `task surveylite:up`. The data stays: `docker rm -f mta-system-prod-surveylite-service-1`.

## Versions of the services

`versions.env` holds the versions of all service images. The app, all `task` commands and the compose files read it. The [README](../README.md#supported-versions-of-the-services) lists the versions. `task services:versions` and the admin page **Services → Auto creation** show them.

To change a version:

1. Change it in `versions.env`.
2. Get the image with its task:

   | Service | Task |
   | --- | --- |
   | Metabase | `task services:pull-metabase` |
   | OpenRefine | `task services:build-openrefine` |
   | WordPress and WP-CLI | `task services:pull-wordpress` |
   | PostgreSQL | `task services:pull-postgresql` |
   | pgAdmin 4 | `task services:pull-pgadmin4` |
   | MariaDB | `task services:pull-mariadb` |
   | sqlmate | Load the image on the server, or `task services:build-sqlmate` (from `temp/sqlmate`) |
   | SurveyLite | Load the image on the server, or `task services:build-surveylite` (from `temp/surveylite`) |

   `task services:update-all` gets all images except sqlmate and SurveyLite.
3. Restart the app.
4. New users get the new version. For an existing user, use **Create again** on the admin page of the service. For PostgreSQL and pgAdmin 4, run `task prod:up`.

Before a new major version:

* PostgreSQL cannot open the data of an older major version. Dump the databases first.
* MariaDB cannot go back to an older version. The LTS version 12.3 cannot open the data of 13.x.
* pgAdmin 4 changes its data on the first start. Back up `pga4volume-service` first.
