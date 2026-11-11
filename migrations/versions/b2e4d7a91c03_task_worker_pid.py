"""worker process of a background task

Revision ID: b2e4d7a91c03
Revises: 3f6a9c2d1e57
Create Date: 2026-11-11 19:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b2e4d7a91c03"
down_revision = "3f6a9c2d1e57"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("background_tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("worker_pid", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("background_tasks", schema=None) as batch_op:
        batch_op.drop_column("worker_pid")
