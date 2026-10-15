"""Real cookie, ownership, concurrency and worker recovery boundaries (offline)."""
from datetime import timedelta
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, update
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models import Campaign, Concept, Job, Membership, Workspace
from app.workspace import principal, workspace_id
from app.clock import utcnow

pytestmark = pytest.mark.real_auth


@pytest.fixture
def secured(tmp_path, monkeypatch):
    import app.security as security
    import app.worker as worker
    import app.telemetry as telemetry
    from app.config import get_settings
    engine = create_engine(f"sqlite:///{tmp_path / 'security.db'}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        db.add(Workspace(id=1, name="Legacy workspace")); db.commit()
    from app import db as database
    for module in (security, worker, telemetry, database):
        monkeypatch.setattr(module, "SessionLocal", factory)
    monkeypatch.setattr(get_settings(), "bootstrap_token_path", str(tmp_path / 'setup-code'))
    security.ensure_bootstrap_token()
    overrides = dict(app.dependency_overrides)
    def scoped_db():
        with factory(info={"workspace_id": workspace_id()}) as db:
            yield db
    app.dependency_overrides[get_db] = scoped_db
    with TestClient(app) as client:
        yield client, factory, security.bootstrap_file().read_text()
    app.dependency_overrides.clear(); app.dependency_overrides.update(overrides)
    engine.dispose()


def owner(secured):
    client, factory, code = secured
    response = client.post('/api/auth/setup', json={"email": "owner@example.com", "password": "secure-owner-password", "name": "Owner", "workspace_name": "My workspace", "setup_token": code})
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return client, factory


def campaign(client):
    response = client.post('/api/campaigns', json={"name": "Merdeka", "brief": "Promote our approved products"})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_bootstrap_and_cookie_protection(secured):
    client, _, code = secured
    assert client.get('/api/campaigns').status_code == 401
    assert client.get('/media/private.png').status_code == 401
    assert client.post('/api/auth/setup', json={"email": "bad@example.com", "password": "secure-owner-password", "name": "Bad", "workspace_name": "Bad", "setup_token": 'x' * 32}).status_code == 403
    client, _ = owner(secured)
    assert 'HttpOnly' in str(client.cookies) or client.cookies.get('agentcy_session')
    missing = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/campaigns', json={"name": "No", "brief": "No"}).status_code == 403
    client.headers['X-CSRF-Token'] = missing
    assert client.post('/api/campaigns', json={"name": "No", "brief": "No"}, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.get('/api/auth/status').json() == {"setup_required": False}
    assert client.post('/api/auth/logout').status_code == 204
    assert client.get('/api/campaigns').status_code == 401


def test_workspace_reads_joins_aggregates_and_writes_are_isolated(secured):
    client, factory = owner(secured)
    first = campaign(client)
    second = client.post('/api/auth/workspaces', json={"name": "Another brand"}).json()['id']
    switched = client.post(f'/api/auth/workspaces/{second}/switch')
    client.headers['X-CSRF-Token'] = switched.json()['csrf_token']
    assert client.get(f'/api/campaigns/{first}').status_code == 404
    assert client.get(f'/api/campaigns/{first}/results').status_code == 404
    assert client.get('/api/campaigns').json() == []
    assert client.get('/api/campaign-directory').json()['total'] == 0
    assert client.get('/api/workspace/overview').json()['counts'] == {}
    assert client.get('/media/legacy.png').status_code == 404
    assert client.get('/media/w/1/private.png').status_code == 404
    with factory(info={"workspace_id": second}) as db:
        db.add(Concept(campaign_id=first, theme="Foreign", format="image", trend_rationale="", brand_rationale="", variation_axes=['a'], variant_count=1))
        with pytest.raises(Exception, match="Related record"):
            db.flush()
        db.rollback()
        assert db.execute(update(Campaign).where(Campaign.id == first).values(name='stolen')).rowcount == 0
    own = campaign(client)
    assert client.get('/api/campaign-directory').json()['total'] == 1
    assert own != first
    assert client.post('/api/conversations', json={'title': 'Foreign campaign', 'campaign_id': first}).status_code == 404


def test_calendar_overview_links_do_not_leak_other_workspace_campaigns(secured):
    from app.calendar_import import import_calendar
    client, factory = owner(secured)
    with factory() as db:
        import_calendar(db)
    params = dict(start='2026-11-01', end='2026-11-30', types='holiday', state='SGR', include_links=True)
    occasion = next(entry for entry in client.get('/api/calendar', params=params).json()['entries'] if entry['title'] == 'Hari Deepavali')
    plan = client.post('/api/marketing-plans', json={'name': 'Private roadmap', 'start_date': '2026-01-01', 'end_date': '2026-12-31'}).json()
    response = client.post(f"/api/marketing-plans/{plan['id']}/items?version={plan['version']}", json=dict(title='Private campaign idea', occasion_id=occasion['entity_id'], strategy='Private strategy', campaign_start='2026-10-25', campaign_end='2026-10-26', preparation_start='2026-10-01', status='planned'))
    assert response.status_code == 201, response.text
    assert client.get('/api/calendar', params=params).json()['linked_items'][0]['title'] == 'Private campaign idea'
    second = client.post('/api/auth/workspaces', json={'name': 'Separate brand'}).json()['id']
    switched = client.post(f'/api/auth/workspaces/{second}/switch')
    client.headers['X-CSRF-Token'] = switched.json()['csrf_token']
    result = client.get('/api/calendar', params=params).json()
    assert any(entry['title'] == 'Hari Deepavali' for entry in result['entries'])
    assert result['linked_items'] == []


def test_roles_revocation_and_no_approval_bypass(secured):
    client, _ = owner(secured)
    identity = campaign(client)
    member = client.post('/api/auth/members', json={"name": "Editor", "email": "editor@example.com", "password": "secure-editor-password", "role": "editor"})
    assert member.status_code == 201
    owner_cookie, owner_csrf = client.cookies.get('agentcy_session'), client.headers['X-CSRF-Token']
    login = client.post('/api/auth/login', json={"email": "editor@example.com", "password": "secure-editor-password"})
    client.headers['X-CSRF-Token'] = login.json()['csrf_token']
    editor_cookie = client.cookies.get('agentcy_session')
    assert client.get('/api/campaigns').status_code == 200
    assert client.post(f'/api/campaigns/{identity}/approve').status_code == 403
    assert client.patch(f'/api/campaigns/{identity}/auto-mode', json={"auto_approve_plan": True}).status_code == 403
    assert client.put('/api/brand-profile', json={}).status_code == 403
    assert client.get('/api/auth/members').status_code == 403
    assert client.post('/api/auth/workspaces', json={'name': 'Escalation attempt'}).status_code == 403
    client.cookies.set('agentcy_session', owner_cookie, domain='testserver.local', path='/')
    client.headers['X-CSRF-Token'] = owner_csrf
    assert client.delete(f"/api/auth/members/{member.json()['id']}").status_code == 204
    client.cookies.set('agentcy_session', editor_cookie, domain='testserver.local', path='/')
    assert client.get('/api/auth/me').status_code == 401


def test_jobs_idempotency_active_resource_and_cancellation(secured):
    client, _ = owner(secured)
    identity = campaign(client)
    payload = {"path": f'/campaigns/{identity}/plan/stream', "request_key": 'same-key-123'}
    first = client.post('/api/jobs', json=payload)
    assert first.status_code == 202, first.text
    assert client.post('/api/jobs', json=payload).json()['id'] == first.json()['id']
    assert client.post('/api/jobs', json={**payload, 'request_key': 'another-key-123'}).json()['id'] == first.json()['id']
    assert client.post('/api/jobs', json={"path": f'/campaigns/{identity}/generate/stream', 'request_key': 'third-key-123'}).status_code == 409
    assert client.post('/api/jobs', json={"path": '/auth/members', 'request_key': 'invalid-op-123'}).status_code == 422
    assert client.post(f"/api/jobs/{first.json()['id']}/cancel").json()['status'] == 'cancelled'
    assert client.post(f"/api/jobs/{first.json()['id']}/retry").status_code == 409
    queued = client.post(f'/api/campaigns/{identity}/plan/stream?unused=1')
    assert queued.status_code == 202 and '__job__' in queued.json()


def test_worker_runs_existing_gate_and_persists_replay(secured):
    from app.api.deps import get_planner
    from app.worker import claim, execute
    from tests.test_api_streaming import NarratingPlanner
    client, factory = owner(secured)
    identity = campaign(client)
    app.dependency_overrides[get_planner] = lambda: NarratingPlanner()
    job_id = client.post('/api/jobs', json={"path": f'/campaigns/{identity}/plan/stream', 'request_key': 'worker-run-123'}).json()['id']
    execute(claim())
    result = client.get(f'/api/jobs/{job_id}').json()
    assert result['status'] == 'succeeded', result
    assert result['result']['concepts']
    assert len(result['events']) >= 2
    assert client.get(f'/api/jobs/{job_id}?after=1').json()['cursor'] == len(result['events'])
    assert client.get(f'/api/campaigns/{identity}').json()['status'] == 'pending_plan_approval'
    assert client.post(f'/api/campaigns/{identity}/approve').status_code == 409


def test_crash_recovery_retains_events_and_releases_resource(secured):
    from app.worker import claim, recover_stale
    client, factory = owner(secured)
    identity = campaign(client)
    job = client.post('/api/jobs', json={"path": f'/campaigns/{identity}/plan/stream', 'request_key': 'crashed-run-123'}).json()
    claimed = claim()
    with factory() as db:
        row = db.get(Job, claimed.id); row.lease_until = utcnow() - timedelta(seconds=1)
        row.events = [{"kind": "event", "agent": "planner", "phase": "started", "detail": "Working"}]
        db.get(Campaign, identity).status = 'planning'; db.commit()
        recover_stale(db)
    saved = client.get(f"/api/jobs/{job['id']}").json()
    assert saved['status'] == 'interrupted' and saved['events']
    assert client.get(f'/api/campaigns/{identity}').json()['status'] == 'draft'
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 202


def test_result_validation_versioning_and_no_double_counting(secured):
    client, _ = owner(secured)
    identity = campaign(client)
    payload = {"channel": "instagram", "period_start": "2026-08-01", "period_end": "2026-08-31", "spend": 100, "revenue": 400, "leads": 10}
    saved = client.post(f'/api/campaigns/{identity}/results', json=payload)
    assert saved.status_code == 200, saved.text
    assert client.post(f'/api/campaigns/{identity}/results', json=payload).status_code == 409
    assert client.post(f'/api/campaigns/{identity}/results', json={**payload, "version": 1, "revenue": 500}).status_code == 200
    assert client.post(f'/api/campaigns/{identity}/results', json={**payload, "period_start": "2026-08-15"}).status_code == 409
    assert client.post(f'/api/campaigns/{identity}/results', json={**payload, "spend": -1}).status_code == 422
    assert client.post(f'/api/campaigns/{identity}/results', json={**payload, "period_end": "2026-01-01"}).status_code == 422


def test_conversations_are_summaries_and_messages_are_paginated(secured):
    from app.models import ChatMessage
    client, factory = owner(secured)
    conversation = client.post('/api/conversations', json={"title": "Long strategy"}).json()['id']
    with factory(info={"workspace_id": 1}) as db:
        db.add_all([ChatMessage(conversation_id=conversation, role='user', content=f'Message {index}') for index in range(120)])
        db.commit()
    listed = client.get('/api/conversations?summary=true').json()
    assert listed[0]['messages'] == [] and listed[0]['message_count'] == 120
    latest = client.get(f'/api/conversations/{conversation}').json()['messages']
    assert len(latest) == 50 and latest[-1]['content'] == 'Message 119'
    earlier = client.get(f"/api/conversations/{conversation}/messages?before={latest[0]['id']}").json()
    assert len(earlier) == 50 and earlier[-1]['id'] < latest[0]['id']


def test_login_throttle_is_persistent_and_password_change_revokes_sessions(secured):
    client, _ = owner(secured)
    for _ in range(5):
        assert client.post('/api/auth/login', json={"email": "owner@example.com", "password": "wrong-password-long"}).status_code == 401
    assert client.post('/api/auth/login', json={"email": "owner@example.com", "password": "secure-owner-password"}).status_code == 429
    assert client.post('/api/auth/password', json={"current_password": "secure-owner-password", "new_password": "changed-owner-password"}).status_code == 204
    assert client.get('/api/auth/me').status_code == 401


def test_knowledge_retrieval_and_replacement_do_not_cross_workspaces(tmp_path):
    from app.rag.store import KnowledgeStore, COMPANY_KB
    from tests.test_store import local_embedder
    first = KnowledgeStore(path=tmp_path / 'kb', embedder=local_embedder, workspace_id=1)
    second = KnowledgeStore(path=tmp_path / 'kb', embedder=local_embedder, workspace_id=2)
    first.ingest_company_kb('# Legacy product\n\nLegacy workspace private facts.', source='brand.md')
    assert second.retrieve_company('private facts') == []
    second.replace_company_kb('# Another product\n\nSecond workspace private facts.', source='brand.md')
    assert first.count(COMPANY_KB) == 1
    assert 'Legacy' in first.retrieve_company('product')[0].text
    assert 'Second' in second.retrieve_company('product')[0].text


def test_meter_enforces_calls_tokens_and_configured_costs():
    from app.telemetry import Meter
    current = Meter(1, 1000)
    current.reserve(200, 100, 100, 'model')
    with pytest.raises(RuntimeError, match='budget'):
        current.reserve(200, 100, 100, 'model')
    priced = Meter(10, 10000, max_cost=0.001, prices={'model': [1, 2]})
    with pytest.raises(RuntimeError, match='pricing'):
        priced.reserve(100, 50, 50, 'unknown')
    estimate = priced.reserve(100, 50, 50, 'model')
    assert estimate == pytest.approx(0.00015)
    priced.settle(100, 80, estimate, 0.00012)
    assert priced.cost == pytest.approx(0.00012)


def test_lost_worker_lease_blocks_late_domain_writes(secured):
    from app.worker import claim
    client, factory = owner(secured)
    identity = campaign(client)
    client.post('/api/jobs', json={"path": f'/campaigns/{identity}/plan/stream', 'request_key': 'fence-test-123'})
    job = claim()
    with factory(info={"workspace_id": 1, "job_id": job.id, "worker_id": 'obsolete-worker'}) as db:
        db.get(Campaign, identity).name = 'Late output'
        with pytest.raises(Exception, match='lease ended'):
            db.flush()


def test_results_reach_the_strategist_calendar_and_campaign_planner(secured):
    from app.performance import performance_context
    from app.calendar_schemas import RunRequest
    from app.marketing_calendar import run_context
    from app.api.deps import Tuning, get_planner
    client, factory = owner(secured)
    identity = campaign(client)
    client.post(f'/api/campaigns/{identity}/results', json={"channel": "instagram", "period_start": "2026-08-01", "period_end": "2026-08-31", "spend": 100, "revenue": 400})
    with factory(info={"workspace_id": 1}) as db:
        report = performance_context(db)
        assert report['records'][0]['roas'] == 4
        context = run_context(db, RunRequest(start_date='2026-10-01', end_date='2027-09-30', operation='annual', states=['KUL'], request_key='results-context-test'))
        assert context['measured_performance']['records'][0]['campaign_id'] == identity
        assert Tuning(db).performance['records'][0]['revenue'] == 400


def test_worker_preserves_legacy_array_results(secured, monkeypatch, tmp_path):
    from app.worker import claim, execute
    from app.api import trends
    from app.trends.scraper import TrendScraper
    class Store:
        def ingest_trends(self, text, source):
            return 1
    scraper = TrendScraper(store=Store(), corpus_dir=tmp_path / "trends", snapshot_dir=tmp_path / "snapshots")
    monkeypatch.setattr(trends, '_scraper', lambda: scraper)
    client, _ = owner(secured)
    assert client.post('/api/trends/sources', json={"keyword": "raya promotion"}).status_code == 201
    queued = client.post('/api/trends/scrape?refresh=false').json()['__job__']
    execute(claim())
    result = client.get(f"/api/jobs/{queued['id']}").json()
    assert result['status'] == 'succeeded', result
    assert isinstance(result['result'], list) and result['result'][0]['mode'] == 'offline'


def test_removed_member_can_be_restored_without_overwriting_credentials(secured):
    from app.models import User
    client, factory = owner(secured)
    payload = {"name": "Teammate", "email": "restore@example.com", "password": "original-member-password", "role": "editor"}
    member = client.post('/api/auth/members', json=payload).json()
    with factory() as db:
        original = db.scalar(select(User).where(User.email == payload['email'])).password_hash
    assert client.delete(f"/api/auth/members/{member['id']}").status_code == 204
    restored = client.post('/api/auth/members', json={"name": "Ignored rename", "email": payload['email'], "role": "viewer"})
    assert restored.status_code == 201 and restored.json()['existing_account'] is True
    with factory() as db:
        user = db.scalar(select(User).where(User.email == payload['email']))
        assert user.password_hash == original and user.name == 'Teammate'
    login = client.post('/api/auth/login', json={"email": payload['email'], "password": payload['password']})
    assert login.status_code == 200 and login.json()['role'] == 'viewer'
