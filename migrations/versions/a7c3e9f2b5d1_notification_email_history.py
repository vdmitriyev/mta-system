"""e-mail subject of a notification, and the e-mail history

Only adds what is missing: some databases got these with an earlier version of
the migration dbf01a43fe44.

Revision ID: a7c3e9f2b5d1
Revises: dbf01a43fe44
Create Date: 2026-11-23 17:00:19

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a7c3e9f2b5d1"
down_revision = "dbf01a43fe44"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()

    columns = {column["name"] for column in inspector.get_columns("notifications")}
    if "email_subject" not in columns:
        with op.batch_alter_table("notifications", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("email_subject", sa.String(length=200), nullable=True)
            )

    if "email_batches" not in tables:
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

    if "email_batch_items" not in tables:
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


def downgrade():
    with op.batch_alter_table("email_batch_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_email_batch_items_batch_id"))
    op.drop_table("email_batch_items")

    with op.batch_alter_table("email_batches", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_email_batches_notification_id"))
        batch_op.drop_index(batch_op.f("ix_email_batches_created_at"))
    op.drop_table("email_batches")

    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_column("email_subject")
