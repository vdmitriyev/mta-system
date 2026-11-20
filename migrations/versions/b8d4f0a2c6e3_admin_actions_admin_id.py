"""admin log: the user ID of the admin instead of the e-mail

Revision ID: b8d4f0a2c6e3
Revises: a7c3e9f1b5d2
Create Date: 2026-11-20 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b8d4f0a2c6e3"
down_revision = "a7c3e9f1b5d2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("admin_actions") as batch_op:
        batch_op.add_column(sa.Column("admin_id", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE admin_actions SET admin_id = "
        "(SELECT users.itid FROM users WHERE users.email = admin_actions.admin_email)"
    )
    with op.batch_alter_table("admin_actions") as batch_op:
        batch_op.drop_column("admin_email")


def downgrade():
    with op.batch_alter_table("admin_actions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "admin_email",
                sa.String(length=255),
                nullable=False,
                server_default="",
            )
        )
    op.execute(
        "UPDATE admin_actions SET admin_email = COALESCE("
        "(SELECT users.email FROM users WHERE users.itid = admin_actions.admin_id), '')"
    )
    with op.batch_alter_table("admin_actions") as batch_op:
        batch_op.drop_column("admin_id")
