"""Persist selected occasion context across strategist messages and reloads."""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
revision = "20261014_chat_context"
down_revision = "20261014_calendar"
branch_labels = None
depends_on = None

def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("conversations")}
    for column, target in (("calendar_occasion_id", "calendar_occasions"), ("calendar_business_event_id", "business_events")):
        if column not in columns:
            op.add_column("conversations", sa.Column(column, sa.Integer(), nullable=True))
            op.create_foreign_key(f"fk_conversations_{column}", "conversations", target, [column], ["id"], ondelete="SET NULL")
            op.create_index(f"ix_conversations_{column}", "conversations", [column])

def downgrade():
    raise RuntimeError("Retain planning context during application rollback; use an explicit backup to remove calendar data.")
