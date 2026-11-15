"""login history, and the user that a background task is about

Revision ID: e3b7c1d9a2f4
Revises: d5f2a9c4e6b1
Create Date: 2026-11-13 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e3b7c1d9a2f4"
down_revision = "d5f2a9c4e6b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_history",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("result", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("itid"),
    )
    with op.batch_alter_table("login_history") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_login_history_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_login_history_created_at"), ["created_at"], unique=False
        )

    with op.batch_alter_table("background_tasks") as batch_op:
        batch_op.add_column(sa.Column("about_user_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_background_tasks_about_user_id"),
            ["about_user_id"],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table("background_tasks") as batch_op:
        batch_op.drop_index(batch_op.f("ix_background_tasks_about_user_id"))
        batch_op.drop_column("about_user_id")

    with op.batch_alter_table("login_history") as batch_op:
        batch_op.drop_index(batch_op.f("ix_login_history_created_at"))
        batch_op.drop_index(batch_op.f("ix_login_history_user_id"))
    op.drop_table("login_history")
