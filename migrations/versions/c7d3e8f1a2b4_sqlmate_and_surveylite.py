"""sqlmate and surveylite: accounts, survey assignments, survey requirements

Revision ID: c7d3e8f1a2b4
Revises: b2e4d7a91c03
Create Date: 2026-11-12 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7d3e8f1a2b4"
down_revision = "b2e4d7a91c03"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sqlmate_service",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("sqlmate_login", sa.String(length=100), nullable=False),
        sa.Column("sqlmate_pin", sa.String(length=50), nullable=True),
        sa.Column("sqlmate_login_url", sa.String(length=500), nullable=True),
        sa.Column("created", sa.Boolean(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.itid"]),
        sa.PrimaryKeyConstraint("itid"),
    )
    op.create_table(
        "surveylite_service",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("surveylite_participant_id", sa.String(length=64), nullable=True),
        sa.Column("surveylite_login", sa.String(length=100), nullable=True),
        sa.Column("surveylite_pin", sa.String(length=50), nullable=True),
        sa.Column("created", sa.Boolean(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.itid"]),
        sa.PrimaryKeyConstraint("itid"),
    )
    op.create_table(
        "survey_assignments",
        sa.Column("itid", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("survey_id", sa.Integer(), nullable=False),
        sa.Column("survey_title", sa.String(length=200), nullable=True),
        sa.Column("survey_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.itid"]),
        sa.PrimaryKeyConstraint("itid"),
        sa.UniqueConstraint("user_id", "survey_id"),
    )
    with op.batch_alter_table("survey_assignments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_survey_assignments_user_id"), ["user_id"], unique=False
        )
    op.create_table(
        "service_requirements",
        sa.Column("service", sa.String(length=50), nullable=False),
        sa.Column("survey_id", sa.Integer(), nullable=False),
        sa.Column("survey_title", sa.String(length=200), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("service"),
    )
    # the switches on the page "Auto creation" (off; kept if they exist)
    for service, description in (("sqlmate", "sqlmate"), ("surveylite", "SurveyLite")):
        op.execute(
            sa.text(
                "INSERT OR IGNORE INTO service_settings (service, create_accounts, "
                "description) VALUES (:service, 0, :description)"
            ).bindparams(service=service, description=description)
        )


def downgrade():
    op.execute(
        "DELETE FROM service_settings WHERE service IN ('sqlmate', 'surveylite')"
    )
    op.drop_table("service_requirements")
    with op.batch_alter_table("survey_assignments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_survey_assignments_user_id"))
    op.drop_table("survey_assignments")
    op.drop_table("surveylite_service")
    op.drop_table("sqlmate_service")
