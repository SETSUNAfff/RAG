"""add streaming lifecycle fields to messages

Revision ID: 0004_message_streaming_fields
Revises: 0003_add_recall_at_20
Create Date: 2026-09-20

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "0004_message_streaming_fields"
down_revision = "0003_add_recall_at_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("messages")}

    if "status" not in columns:
        op.add_column(
            "messages",
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="completed",
            ),
        )
    if "reply_to_message_id" not in columns:
        op.add_column(
            "messages",
            sa.Column("reply_to_message_id", sa.BigInteger(), nullable=True),
        )
    if "suggested_questions" not in columns:
        op.add_column(
            "messages",
            sa.Column("suggested_questions", sa.JSON(), nullable=True),
        )
    if "trace_id" not in columns:
        op.add_column(
            "messages",
            sa.Column("trace_id", sa.String(length=32), nullable=True),
        )

    inspector = inspect(bind)
    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("messages")
    }
    if "fk_messages_reply_to_message_id" not in foreign_keys:
        op.create_foreign_key(
            "fk_messages_reply_to_message_id",
            "messages",
            "messages",
            ["reply_to_message_id"],
            ["id"],
            ondelete="SET NULL",
        )

    indexes = {index["name"] for index in inspector.get_indexes("messages")}
    if "ux_messages_reply_to_message_id" not in indexes:
        op.create_index(
            "ux_messages_reply_to_message_id",
            "messages",
            ["reply_to_message_id"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("messages")}
    if "ux_messages_reply_to_message_id" in indexes:
        op.drop_index("ux_messages_reply_to_message_id", table_name="messages")

    foreign_keys = {
        foreign_key.get("name")
        for foreign_key in inspector.get_foreign_keys("messages")
    }
    if "fk_messages_reply_to_message_id" in foreign_keys:
        op.drop_constraint(
            "fk_messages_reply_to_message_id",
            "messages",
            type_="foreignkey",
        )

    columns = {column["name"] for column in inspector.get_columns("messages")}
    for column_name in (
        "trace_id",
        "suggested_questions",
        "reply_to_message_id",
        "status",
    ):
        if column_name in columns:
            op.drop_column("messages", column_name)
