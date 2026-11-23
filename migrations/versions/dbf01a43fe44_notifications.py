"""notifications for the users, who read them, and their e-mails (with a history)

Automatic notifications start hidden (shown_at empty) until an admin shows them.

Revision ID: dbf01a43fe44
Revises: c9e5a1b3d7f4
Create Date: 2026-11-22 19:57:23.743838

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "dbf01a43fe44"
down_revision = "c9e5a1b3d7f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("audience", sa.String(length=50), nullable=True),
        sa.Column("event_key", sa.String(length=100), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("shown_at", sa.DateTime(), nullable=True),
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
        sa.Column("email_test_at", sa.DateTime(), nullable=True),
        sa.Column("email_test_to", sa.String(length=100), nullable=True),
        sa.Column("emailed_at", sa.DateTime(), nullable=True),
        sa.Column("emailed_count", sa.Integer(), nullable=False),
        sa.Column("email_subject", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.itid"],
        ),
        sa.PrimaryKeyConstraint("itid"),
        sa.UniqueConstraint("event_key"),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notifications_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_shown_at"), ["shown_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_notifications_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "notification_reads",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "read_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.itid"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.itid"],
        ),
        sa.PrimaryKeyConstraint("itid"),
        sa.UniqueConstraint("notification_id", "user_id"),
    )
    with op.batch_alter_table("notification_reads", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_notification_reads_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "notification_emails",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"], ["notifications.itid"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.itid"],
        ),
        sa.PrimaryKeyConstraint("itid"),
        sa.UniqueConstraint("notification_id", "user_id"),
    )

    op.create_table(
        "email_batches",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("itid"),
    )
    with op.batch_alter_table("email_batches", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_email_batches_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_email_batches_notification_id"),
            ["notification_id"],
            unique=False,
        )

    op.create_table(
        "email_batch_items",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["email_batches.itid"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("itid"),
    )
    with op.batch_alter_table("email_batch_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_email_batch_items_batch_id"), ["batch_id"], unique=False
        )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("email_batch_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_email_batch_items_batch_id"))

    op.drop_table("email_batch_items")
    with op.batch_alter_table("email_batches", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_email_batches_notification_id"))
        batch_op.drop_index(batch_op.f("ix_email_batches_created_at"))

    op.drop_table("email_batches")
    op.drop_table("notification_emails")
    with op.batch_alter_table("notification_reads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notification_reads_user_id"))

    op.drop_table("notification_reads")
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notifications_shown_at"))
        batch_op.drop_index(batch_op.f("ix_notifications_user_id"))
        batch_op.drop_index(batch_op.f("ix_notifications_created_at"))

    op.drop_table("notifications")
    # ### end Alembic commands ###
