"""background tasks

Revision ID: 8c1d2e7a4b90
Revises: 5ffaa94a0270
Create Date: 2026-11-10 21:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8c1d2e7a4b90"
down_revision = "5ffaa94a0270"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "background_tasks",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.itid"]),
        sa.PrimaryKeyConstraint("itid"),
        sa.UniqueConstraint("public_id"),
    )
    with op.batch_alter_table("background_tasks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_background_tasks_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_background_tasks_user_id"), ["user_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("background_tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_background_tasks_user_id"))
        batch_op.drop_index(batch_op.f("ix_background_tasks_status"))
    op.drop_table("background_tasks")
