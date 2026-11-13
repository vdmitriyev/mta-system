"""surveylite: personal login links of the participants and of the surveys

Revision ID: d5f2a9c4e6b1
Revises: c7d3e8f1a2b4
Create Date: 2026-11-12 19:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d5f2a9c4e6b1"
down_revision = "c7d3e8f1a2b4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("surveylite_service") as batch_op:
        batch_op.add_column(
            sa.Column("surveylite_login_url", sa.String(length=500), nullable=True)
        )
    with op.batch_alter_table("survey_assignments") as batch_op:
        batch_op.add_column(
            sa.Column("survey_auth_url", sa.String(length=500), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("survey_assignments") as batch_op:
        batch_op.drop_column("survey_auth_url")
    with op.batch_alter_table("surveylite_service") as batch_op:
        batch_op.drop_column("surveylite_login_url")
