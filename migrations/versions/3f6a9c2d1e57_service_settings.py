"""service settings in the database

The switches CREATE_<NAME>_SERVICE moved from the env file to the table
service_settings (admin page "Service accounts"). The values that are set now
(environment or env file) are copied once.

Revision ID: 3f6a9c2d1e57
Revises: 8c1d2e7a4b90
Create Date: 2026-11-11 18:00:00.000000

"""

import os

import sqlalchemy as sa
from alembic import op
from dotenv import dotenv_values

# revision identifiers, used by Alembic.
revision = "3f6a9c2d1e57"
down_revision = "8c1d2e7a4b90"
branch_labels = None
depends_on = None

# (service, old environment variable, description)
SERVICES = [
    ("postgresql", "CREATE_POSTGRESQL_SERVICE", "PostgreSQL: own database"),
    ("pgadmin4", "CREATE_PG4ADMIN_SERVICE", "pgAdmin 4: login (needs PostgreSQL)"),
    ("metabase", "CREATE_METABASE_SERVICE", "Metabase: own container"),
    ("openrefine", "CREATE_OPENREFINE_SERVICE", "OpenRefine: own container"),
    ("mariadb", "CREATE_MARIADB_SERVICE", "MariaDB: own database"),
    (
        "wordpress",
        "CREATE_WORDPRESS_SERVICE",
        "WordPress: own container (needs MariaDB)",
    ),
    ("nifi", "CREATE_NIFI_SERVICE", "NiFi: own container"),
    ("superset", "CREATE_SUPERSET_SERVICE", "Superset: login"),
    (
        "jupyterhub",
        "CREATE_JUPYTERHUB_SERVICE",
        "JupyterHub: login (an admin creates the account in JupyterHub)",
    ),
]


def old_values() -> dict:
    """Values of the old variables: the environment wins over the env file"""

    from app.config import env_file

    path = env_file()
    values = dict(dotenv_values(path)) if path.is_file() else {}
    values.update(os.environ)
    return {key.upper(): value for key, value in values.items() if value is not None}


def is_on(value: str | None) -> bool:
    return (value or "").strip().lower() in ("true", "1", "yes", "on")


def upgrade():
    table = op.create_table(
        "service_settings",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("service", sa.String(length=50), nullable=False),
        sa.Column("create_accounts", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("itid"),
        sa.UniqueConstraint("service"),
    )
    values = old_values()
    op.bulk_insert(
        table,
        [
            {
                "service": service,
                "create_accounts": is_on(values.get(variable)),
                "description": description,
            }
            for service, variable, description in SERVICES
        ],
    )


def downgrade():
    op.drop_table("service_settings")
