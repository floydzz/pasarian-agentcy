"""Exercise the shipped additive migration against an existing pre-calendar schema."""
from __future__ import annotations
from sqlalchemy import MetaData, inspect, select, text
from app import db as database
from app.db import Base
from app.models import Campaign

NEW = {'worker_heartbeats', 'workspaces', 'users', 'memberships', 'login_sessions', 'login_attempts', 'jobs', 'ai_calls', 'campaign_results', 'calendar_occasions','business_events','marketing_preferences','marketing_plans','marketing_plan_items','marketing_tasks','calendar_runs'}
FIELDS = {'conversations': {'marketing_plan_id','marketing_plan_item_id','calendar_occasion_id','calendar_business_event_id'}, 'chat_messages': {'calendar_run_id'}}


def test_existing_campaigns_and_conversations_survive_calendar_upgrade(engine, monkeypatch):
    # This fixture is the disposable agentcy_test database, never application data.
    legacy = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in NEW:
            copied = table.to_metadata(legacy)
            removed = FIELDS.get(table.name, set()) | ({'workspace_id'} if 'workspace_id' in copied.c else set())
            for constraint in list(copied.constraints):
                if any(column.name in removed for column in getattr(constraint, 'columns', [])):
                    copied.constraints.remove(constraint)
            for foreign_key in list(copied.foreign_keys):
                if foreign_key.parent.name in removed:
                    copied.foreign_keys.remove(foreign_key)
            for index in list(copied.indexes):
                if any(column.name in removed for column in index.columns): copied.indexes.remove(index)
            for name in removed: copied._columns.remove(copied.c[name])
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        connection.execute(text('DROP TABLE IF EXISTS alembic_version'))
        legacy.create_all(connection)
        cid = connection.execute(legacy.tables['campaigns'].insert().values(name='Existing campaign',brief='Keep the approved business brief',status='draft',auto_approve_plan=False,auto_approve_assets=False)).inserted_primary_key[0]
        tid = connection.execute(legacy.tables['conversations'].insert().values(title='Existing strategy',campaign_id=cid)).inserted_primary_key[0]
        connection.execute(legacy.tables['chat_messages'].insert().values(conversation_id=tid,role='user',content='Keep this conversation'))
    monkeypatch.setattr(database, 'engine', engine)
    database.create_all()
    database.create_all()  # Startup must be repeatable.
    with engine.begin() as connection:
        assert connection.scalar(select(Campaign.name).where(Campaign.id == cid)) == 'Existing campaign'
        assert connection.execute(text('SELECT content FROM chat_messages WHERE conversation_id=:id'), {'id':tid}).scalar() == 'Keep this conversation'
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar() == '20261015_workspaces'
        assert connection.execute(text('SELECT workspace_id FROM campaigns WHERE id=:id'), {'id':cid}).scalar() == 1
        assert connection.execute(text('SELECT COUNT(*) FROM memberships')).scalar() == 0
        assert FIELDS['conversations'] <= {column['name'] for column in inspect(connection).get_columns('conversations')}
        targets = {fk['referred_table'] for fk in inspect(connection).get_foreign_keys('conversations')}
        assert {'campaigns','marketing_plans','marketing_plan_items','calendar_occasions','business_events'} <= targets
        connection.execute(text('DELETE FROM chat_messages WHERE conversation_id=:id'), {'id':tid})
        connection.execute(text('DELETE FROM conversations WHERE id=:id'), {'id':tid})
        connection.execute(text('DELETE FROM campaigns WHERE id=:id'), {'id':cid})
