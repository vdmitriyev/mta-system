=======
History
=======

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
