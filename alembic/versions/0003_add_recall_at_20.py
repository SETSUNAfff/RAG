"""add recall_at_20 metric

Revision ID: 0003_add_recall_at_20
Revises: 0002_evaluation_tables
Create Date: 2026-08-26

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "0003_add_recall_at_20"
down_revision = "0002_evaluation_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in inspect(bind).get_columns("evaluation_run_results")
    }
    if "recall_at_20" not in columns:
        op.add_column(
            "evaluation_run_results",
            sa.Column("recall_at_20", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {
        column["name"]
        for column in inspect(bind).get_columns("evaluation_run_results")
    }
    if "recall_at_20" in columns:
        op.drop_column("evaluation_run_results", "recall_at_20")
