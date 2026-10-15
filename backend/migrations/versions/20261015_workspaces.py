"""Workspace ownership, revocable sessions, durable jobs and campaign outcomes.

Existing records are assigned to workspace 1. Initial ownership requires a
local setup token; an arbitrary first visitor cannot claim legacy data.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261015_workspaces"
down_revision = "20261014_chat_context"
branch_labels = None
depends_on = None

_LATE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("marketing_videos", "campaign_id", "INTEGER NULL"),
    ("marketing_videos", "use_broll", "BOOLEAN NOT NULL DEFAULT 0"),
    ("cinematic_trailer_shots", "product_surface", "VARCHAR(32) NOT NULL DEFAULT 'none'"),
    ("cinematic_trailers", "application_capture_url", "VARCHAR(1000) NULL"),
    ("cinematic_trailers", "soundtrack_url", "VARCHAR(1000) NULL"),
    ("cinematic_trailers", "product_reference_url", "VARCHAR(1000) NULL"),
    ("cinematic_trailers", "campaign_id", "INTEGER NULL"),
    ("marketing_videos", "product_reference_url", "VARCHAR(1000) NULL"),
    ("agent_settings", "context_turns", "INTEGER NULL"),
)


OWNED_TABLES = ('agent_settings', 'brand_profiles', 'business_events', 'campaigns', 'demo_videos', 'jobs', 'marketing_plans', 'marketing_preferences', 'trend_sources', 'ai_calls', 'calendar_runs', 'campaign_results', 'cinematic_trailers', 'concepts', 'marketing_plan_items', 'marketing_videos', 'product_references', 'runs', 'cinematic_trailer_shots', 'conversations', 'marketing_tasks', 'variants', 'assets', 'chat_messages')


def upgrade():
    bind = op.get_bind()
    # The legacy application used create_all. Reconcile its additive fields
    # once, under migration history, before introducing ownership.
    for name, column, ddl in _LATE_COLUMNS:
        if name in sa.inspect(bind).get_table_names() and column not in {c["name"] for c in sa.inspect(bind).get_columns(name)}:
            op.execute(sa.text(f"ALTER TABLE {name} ADD COLUMN {column} {ddl}"))
    _create_workspace(bind)
    if not bind.scalar(sa.text("SELECT id FROM workspaces WHERE id=1")):
        bind.execute(sa.text("INSERT INTO workspaces (id, name, token_limit_per_job, call_limit_per_job, llm_prices) VALUES (1, 'Existing workspace', 250000, 100, '{}')"))
    existing = set(sa.inspect(bind).get_table_names())
    for name in OWNED_TABLES:
        if name in existing and "workspace_id" not in {c["name"] for c in sa.inspect(bind).get_columns(name)}:
            op.add_column(name, sa.Column("workspace_id", sa.Integer(), nullable=False, server_default="1"))
            op.create_foreign_key(f"fk_{name}_workspace", name, "workspaces", ["workspace_id"], ["id"])
            op.create_index(f"ix_{name}_workspace_id", name, ["workspace_id"])
    for name, column, constraint in (("agent_settings", "agent", "uq_workspace_agent"), ("calendar_runs", "request_key", "uq_workspace_calendar_key")):
        inspector = sa.inspect(bind)
        for index in inspector.get_indexes(name):
            if index.get("unique") and index["column_names"] == [column]:
                op.drop_index(index["name"], table_name=name)
        unique = sa.inspect(bind).get_unique_constraints(name)
        if not any(row["name"] == constraint for row in unique):
            op.create_unique_constraint(constraint, name, ["workspace_id", column])
    _create_new_tables(bind)
    indexes = {row["name"] for row in sa.inspect(bind).get_indexes("jobs")}
    for name, columns in (("ix_jobs_claim", ["status", "created_at", "id"]), ("ix_jobs_lease", ["status", "lease_until"])):
        if name not in indexes:
            op.create_index(name, "jobs", columns)


def downgrade():
    raise RuntimeError("Ownership cannot be discarded safely. Restore the verified pre-upgrade backup to roll back the schema.")


def _create_workspace(bind):
    if "workspaces" not in sa.inspect(bind).get_table_names():
        op.create_table('workspaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('token_limit_per_job', sa.Integer(), nullable=False),
        sa.Column('call_limit_per_job', sa.Integer(), nullable=False),
        sa.Column('max_llm_cost_per_job', sa.Float(), nullable=True),
        sa.Column('llm_prices', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )


def _create_new_tables(bind):
    if "login_attempts" not in sa.inspect(bind).get_table_names():
        op.create_table('login_attempts',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('reset_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('key')
        )
    if "users" not in sa.inspect(bind).get_table_names():
        op.create_table('users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('disabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
        )
    if "worker_heartbeats" not in sa.inspect(bind).get_table_names():
        op.create_table('worker_heartbeats',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_worker_heartbeats_last_seen'), 'worker_heartbeats', ['last_seen'], unique=False)
    if "jobs" not in sa.inspect(bind).get_table_names():
        op.create_table('jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('request_key', sa.String(length=80), nullable=False),
        sa.Column('active_key', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('lease_until', sa.DateTime(), nullable=True),
        sa.Column('worker_id', sa.String(length=36), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'active_key', name='uq_job_active'),
        sa.UniqueConstraint('workspace_id', 'request_key', name='uq_job_request')
        )
        op.create_index(op.f('ix_jobs_lease_until'), 'jobs', ['lease_until'], unique=False)
        op.create_index(op.f('ix_jobs_status'), 'jobs', ['status'], unique=False)
        op.create_index(op.f('ix_jobs_workspace_id'), 'jobs', ['workspace_id'], unique=False)
    if "login_sessions" not in sa.inspect(bind).get_table_names():
        op.create_table('login_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('csrf', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash')
        )
        op.create_index(op.f('ix_login_sessions_user_id'), 'login_sessions', ['user_id'], unique=False)
    if "memberships" not in sa.inspect(bind).get_table_names():
        op.create_table('memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'workspace_id', name='uq_membership')
        )
    if "ai_calls" not in sa.inspect(bind).get_table_names():
        op.create_table('ai_calls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=True),
        sa.Column('provider', sa.String(length=80), nullable=False),
        sa.Column('model', sa.String(length=120), nullable=False),
        sa.Column('prompt_version', sa.String(length=64), nullable=False),
        sa.Column('schema_name', sa.String(length=100), nullable=False),
        sa.Column('request_id', sa.String(length=255), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('error_code', sa.String(length=80), nullable=True),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('estimated_cost_usd', sa.Float(), nullable=True),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_ai_calls_job_id'), 'ai_calls', ['job_id'], unique=False)
        op.create_index(op.f('ix_ai_calls_workspace_id'), 'ai_calls', ['workspace_id'], unique=False)
    if "campaign_results" not in sa.inspect(bind).get_table_names():
        op.create_table('campaign_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=40), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('spend', sa.Float(), nullable=False),
        sa.Column('revenue', sa.Float(), nullable=False),
        sa.Column('impressions', sa.Integer(), nullable=False),
        sa.Column('engagements', sa.Integer(), nullable=False),
        sa.Column('leads', sa.Integer(), nullable=False),
        sa.Column('sales', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'campaign_id', 'channel', 'period_start', 'period_end', name='uq_result_period')
        )
        op.create_index(op.f('ix_campaign_results_campaign_id'), 'campaign_results', ['campaign_id'], unique=False)
        op.create_index(op.f('ix_campaign_results_workspace_id'), 'campaign_results', ['workspace_id'], unique=False)
