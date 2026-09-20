"""add evaluation tables

Revision ID: 0002_evaluation_tables
Revises: 0001_initial
Create Date: 2026-08-24

"""
import sqlalchemy as sa
from alembic import op


revision = "0002_evaluation_tables"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("expected_document_titles", sa.JSON(), nullable=True),
        sa.Column("expected_source_text", sa.Text(), nullable=True),
        sa.Column("expected_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("chapter", sa.String(length=255), nullable=True),
        sa.Column(
            "difficulty",
            sa.String(length=32),
            server_default="medium",
            nullable=False,
        ),
        sa.Column("source_file", sa.String(length=512), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_cases_external_id", "evaluation_cases", ["external_id"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "total_cases",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "completed_cases",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("metrics_summary", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "evaluation_run_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=32), nullable=True),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("retrieved_document_ids", sa.JSON(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("citation_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("retrieval_precision", sa.Float(), nullable=True),
        sa.Column("retrieval_recall", sa.Float(), nullable=True),
        sa.Column("mrr", sa.Float(), nullable=True),
        sa.Column("hit", sa.Boolean(), nullable=True),
        sa.Column("rouge_l", sa.Float(), nullable=True),
        sa.Column("embedding_sim", sa.Float(), nullable=True),
        sa.Column("citation_precision", sa.Float(), nullable=True),
        sa.Column("citation_recall", sa.Float(), nullable=True),
        sa.Column("stale", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evaluation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["evaluation_cases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_run_results_run_id",
        "evaluation_run_results",
        ["run_id"],
    )
    op.create_index(
        "ix_evaluation_run_results_case_id",
        "evaluation_run_results",
        ["case_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evaluation_run_results_case_id",
        table_name="evaluation_run_results",
    )
    op.drop_index(
        "ix_evaluation_run_results_run_id",
        table_name="evaluation_run_results",
    )
    op.drop_table("evaluation_run_results")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_evaluation_cases_external_id", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
