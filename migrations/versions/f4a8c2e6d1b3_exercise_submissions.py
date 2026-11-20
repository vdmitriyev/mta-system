"""file submissions of the exercises and deadline extensions

Revision ID: f4a8c2e6d1b3
Revises: e3b7c1d9a2f4
Create Date: 2026-11-20 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f4a8c2e6d1b3"
down_revision = "e3b7c1d9a2f4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("exercises") as batch_op:
        batch_op.add_column(
            sa.Column(
                "has_submission",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "submission_email",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )

    op.create_table(
        "exercise_submissions",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=255), nullable=False),
        sa.Column("folder", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.itid"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.itid"]),
        sa.PrimaryKeyConstraint("itid"),
    )
    with op.batch_alter_table("exercise_submissions") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exercise_submissions_exercise_id"),
            ["exercise_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_exercise_submissions_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "submission_extensions",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("deadline", sa.DateTime(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.itid"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.itid"]),
        sa.PrimaryKeyConstraint("itid"),
        sa.UniqueConstraint("exercise_id", "user_id"),
    )
    with op.batch_alter_table("submission_extensions") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_submission_extensions_user_id"), ["user_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("submission_extensions") as batch_op:
        batch_op.drop_index(batch_op.f("ix_submission_extensions_user_id"))
    op.drop_table("submission_extensions")

    with op.batch_alter_table("exercise_submissions") as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercise_submissions_user_id"))
        batch_op.drop_index(batch_op.f("ix_exercise_submissions_exercise_id"))
    op.drop_table("exercise_submissions")

    with op.batch_alter_table("exercises") as batch_op:
        batch_op.drop_column("submission_email")
        batch_op.drop_column("has_submission")
