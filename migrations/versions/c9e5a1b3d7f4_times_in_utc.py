"""times in UTC: deadlines, deleted files and background tasks were local times

Revision ID: c9e5a1b3d7f4
Revises: b8d4f0a2c6e3
Create Date: 2026-11-20 21:00:00.000000

Uses the time zone of the server (TZ), as the app did when it wrote the times.
"""

import sqlalchemy as sa
from alembic import op

from app.timeutil import to_local, to_utc

# revision identifiers, used by Alembic.
revision = "c9e5a1b3d7f4"
down_revision = "b8d4f0a2c6e3"
branch_labels = None
depends_on = None

# table -> columns that the app wrote in local time
LOCAL_COLUMNS = {
    "exercises": ("submission_deadline",),
    "submission_extensions": ("deadline",),
    "exercise_submissions": ("deleted_at",),
    "background_tasks": ("started_at", "finished_at"),
}


def _convert(convert):
    connection = op.get_bind()
    for table_name, columns in LOCAL_COLUMNS.items():
        table = sa.table(
            table_name,
            sa.column("itid", sa.Integer),
            *(sa.column(name, sa.DateTime) for name in columns),
        )
        for row in connection.execute(sa.select(table)).mappings():
            values = {
                name: convert(row[name]) for name in columns if row[name] is not None
            }
            if values:
                connection.execute(
                    table.update().where(table.c.itid == row["itid"]).values(**values)
                )


def upgrade():
    _convert(to_utc)


def downgrade():
    _convert(to_local)
