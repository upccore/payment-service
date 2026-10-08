"""add outbox unpublished index

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08

"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )


def downgrade():
    op.drop_index("ix_outbox_unpublished", table_name="outbox")
