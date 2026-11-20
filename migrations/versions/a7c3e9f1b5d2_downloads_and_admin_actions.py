"""downloads for the users and the log of the admin actions

Revision ID: a7c3e9f1b5d2
Revises: f4a8c2e6d1b3
Create Date: 2026-11-20 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c3e9f1b5d2"
down_revision = "f4a8c2e6d1b3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "downloads",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("exercise_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.itid"]),
        sa.PrimaryKeyConstraint("itid"),
    )
    op.create_index("ix_downloads_exercise_id", "downloads", ["exercise_id"])

    op.create_table(
        "admin_actions",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("admin_email", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("exercise_code", sa.String(length=20), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("itid"),
    )
    op.create_index("ix_admin_actions_created_at", "admin_actions", ["created_at"])
    op.create_index("ix_admin_actions_user_id", "admin_actions", ["user_id"])


def downgrade():
    op.drop_index("ix_admin_actions_user_id", table_name="admin_actions")
    op.drop_index("ix_admin_actions_created_at", table_name="admin_actions")
    op.drop_table("admin_actions")
    op.drop_index("ix_downloads_exercise_id", table_name="downloads")
    op.drop_table("downloads")
