"""Calendar schema; reconcile additive fields without resetting existing records."""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "20261014_calendar"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "calendar_occasions" not in existing:
        op.create_table('calendar_occasions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_key', sa.String(length=160), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=24), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('states', sa.JSON(), nullable=False),
        sa.Column('source_url', sa.String(length=1000), nullable=False),
        sa.Column('source_revision', sa.String(length=80), nullable=False),
        sa.Column('verified_at', sa.String(length=40), nullable=False),
        sa.Column('publication_status', sa.String(length=24), nullable=False),
        sa.Column('observed_for', sa.String(length=160), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_key')
        )
        op.create_index('ix_calendar_occasions_end_date', 'calendar_occasions', ['end_date'], unique=False)
        op.create_index('ix_calendar_occasions_start_date', 'calendar_occasions', ['start_date'], unique=False)
    if "business_events" not in existing:
        op.create_table('business_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('archived', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_business_events_start_date', 'business_events', ['start_date'], unique=False)
        op.create_index('ix_business_events_end_date', 'business_events', ['end_date'], unique=False)
    if "marketing_preferences" not in existing:
        op.create_table('marketing_preferences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
    if "marketing_plans" not in existing:
        op.create_table('marketing_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('goals', sa.Text(), nullable=False),
        sa.Column('constraints', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_marketing_plans_start_date', 'marketing_plans', ['start_date'], unique=False)
    if "marketing_plan_items" not in existing:
        op.create_table('marketing_plan_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('occasion_id', sa.Integer(), nullable=True),
        sa.Column('business_event_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('strategy', sa.Text(), nullable=False),
        sa.Column('audience', sa.Text(), nullable=False),
        sa.Column('products', sa.JSON(), nullable=False),
        sa.Column('offer', sa.Text(), nullable=False),
        sa.Column('budget', sa.Float(), nullable=True),
        sa.Column('campaign_start', sa.Date(), nullable=False),
        sa.Column('campaign_end', sa.Date(), nullable=False),
        sa.Column('preparation_start', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=True),
        sa.Column('source_snapshot', sa.JSON(), nullable=False),
        sa.Column('campaign_snapshot', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['business_event_id'], ['business_events.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['occasion_id'], ['calendar_occasions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['plan_id'], ['marketing_plans.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id')
        )
        op.create_index('ix_plan_item_start', 'marketing_plan_items', ['plan_id', 'campaign_start'], unique=False)
    if "marketing_tasks" not in existing:
        op.create_table('marketing_tasks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('offset_days', sa.Integer(), nullable=False),
        sa.Column('manual_date', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['marketing_plan_items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_task_status_due', 'marketing_tasks', ['status', 'due_date'], unique=False)
        op.create_index('ix_marketing_tasks_item_id', 'marketing_tasks', ['item_id'], unique=False)
    if "calendar_runs" not in existing:
        op.create_table('calendar_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_key', sa.String(length=80), nullable=False),
        sa.Column('input', sa.JSON(), nullable=False),
        sa.Column('proposal', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('elapsed_ms', sa.Integer(), nullable=True),
        sa.Column('usage', sa.JSON(), nullable=False),
        sa.Column('accepted_plan_id', sa.Integer(), nullable=True),
        sa.Column('accepted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['accepted_plan_id'], ['marketing_plans.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('request_key')
        )
        op.create_index('ix_calendar_runs_status', 'calendar_runs', ['status'], unique=False)
    inspector = sa.inspect(op.get_bind())
    for table, column, target in (
        ("conversations", "marketing_plan_id", "marketing_plans"),
        ("conversations", "marketing_plan_item_id", "marketing_plan_items"),
        ("chat_messages", "calendar_run_id", "calendar_runs"),
    ):
        columns = {c["name"] for c in inspector.get_columns(table)}
        if column not in columns:
            op.add_column(table, sa.Column(column, sa.Integer(), nullable=True))
            op.create_foreign_key(f"fk_{table}_{column}", table, target, [column], ["id"], ondelete="SET NULL")
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    raise RuntimeError("Calendar data is retained on application rollback. Restore an explicit pre-migration backup to remove it.")
