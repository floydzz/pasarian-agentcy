"""Calendar planning through existing approval gates, entirely offline."""
from __future__ import annotations
import json
from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.agents.calendar_planner import CalendarPlanner
from app.agents.chat import CalendarIntent, ChatAction, ChatTurn
from app.api.calendar import get_calendar_planner
from app.api.deps import get_crew, get_marketing_chat, get_planner, get_storage, get_studio
from app.calendar_import import import_calendar
from app.db import get_db
from app.llm.demo import DemoProvider
from app.main import app
from app.models import CalendarOccasion, CalendarRun, Campaign, MarketingPlanItem, MarketingTask
from app.media.demo import DemoMediaProvider
from app.media.storage import AssetStorage
from app.agents.studio import Studio
from tests.test_api_assets import PassingQA
from tests.test_api_campaigns import StubPlanner
from tests.test_api_generation import StubCrew
from tests.test_api_chat import StubStrategist

@pytest.fixture
def client(session, monkeypatch, tmp_path):
    monkeypatch.setattr('app.llm.demo.LATENCY_SECONDS', 0)
    import_calendar(session)
    storage = AssetStorage(tmp_path / 'media')
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_calendar_planner] = lambda: CalendarPlanner(provider=DemoProvider())
    app.dependency_overrides[get_planner] = lambda: StubPlanner()
    app.dependency_overrides[get_crew] = lambda: StubCrew()
    app.dependency_overrides[get_studio] = lambda: Studio(provider=DemoMediaProvider(), qa=PassingQA(), storage=storage)
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as c: yield c
    app.dependency_overrides.clear()


def request_payload(**overrides):
    return {**dict(operation='annual', start_date='2027-01-01', end_date='2027-12-31', instructions='Plan relevant marketing occasions', request_key=str(uuid4())), **overrides}


def planned(client, **overrides):
    response = client.post('/api/calendar/runs', json=request_payload(**overrides))
    assert response.status_code == 201, response.text
    run = response.json()
    response = client.post(f"/api/calendar/runs/{run['id']}/stream")
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert lines[-1]['kind'] == 'result', lines
    return lines[-1]['run']


def accept(client, run):
    response = client.post(f"/api/calendar/runs/{run['id']}/accept", json={'name': '2027 test roadmap', 'expected_version': run['input']['plan_version']})
    assert response.status_code == 200, response.text
    return response.json()


def item_payload(item):
    keys = ('occasion_id','business_event_id','title','rationale','strategy','audience','products','offer','budget','campaign_start','campaign_end','preparation_start','status','version')
    return {**{k: item[k] for k in keys}, 'tasks': [{'title': t['title'], 'due_date': t['due_date']} for t in item['tasks']]}


def test_state_applicability_and_date_coverage(client):
    def entries(state): return client.get('/api/calendar', params={'start':'2027-01-01','end':'2027-12-31','state':state}).json()
    sarawak, selangor = entries('SWK'), entries('SGR')
    assert not any('Deepavali' in e['title'] for e in sarawak['entries'])
    assert any('Deepavali' in e['title'] for e in selangor['entries'])
    assert any('Gawai' in e['title'] for e in sarawak['entries'])
    assert not any('Gawai' in e['title'] for e in selangor['entries'])
    assert 'school' in selangor['coverage']['2027']['categories']
    assert client.get('/api/calendar?start=2028-01-01&end=2028-12-31&state=SGR').json()['coverage']['2028']['categories'] == []


def test_calendar_validation_and_empty_filter(client):
    for params in ('start=2027-12-31&end=2027-01-01','start=2027-01-01&end=2029-01-01','start=2027-01-01&end=2027-12-31&state=INVALID'):
        assert client.get('/api/calendar?'+params).status_code == 422
    assert client.get('/api/calendar?start=2027-01-01&end=2027-12-31&types=none').json()['entries'] == []


def test_overview_links_campaigns_by_source_even_outside_displayed_month(client, session):
    occasion = session.scalar(select(CalendarOccasion).where(CalendarOccasion.title == 'Hari Deepavali', CalendarOccasion.start_date == date(2026, 11, 8)))
    plan = client.post('/api/marketing-plans', json={'name': 'Festival roadmap', 'start_date': '2026-01-01', 'end_date': '2026-12-31'}).json()
    body = dict(title='Earlier festival launch', occasion_id=occasion.id, strategy='Use approved brand facts', campaign_start='2026-10-25', campaign_end='2026-10-26', preparation_start='2026-10-01', status='planned')
    response = client.post(f"/api/marketing-plans/{plan['id']}/items?version={plan['version']}", json=body)
    assert response.status_code == 201, response.text
    item = response.json()
    campaign = client.post(f"/api/marketing-plan-items/{item['id']}/campaign", json={'version': item['version']}).json()
    params = dict(start='2026-11-01', end='2026-11-30', state='SGR')
    legacy = client.get('/api/calendar', params=params).json()
    assert 'linked_items' not in legacy
    result = client.get('/api/calendar', params={**params, 'include_links': True}).json()
    assert not any(entry['kind'] == 'plan' for entry in result['entries'])
    link = next(link for link in result['linked_items'] if link['id'] == item['id'])
    assert link['occasion_id'] == occasion.id and link['campaign_id'] == campaign['campaign_id']
    assert link['campaign_status'] == 'draft' and link['source_changed'] is False
    thread = client.post('/api/conversations', json={'title': 'Continue festival', 'campaign_id': campaign['campaign_id'], 'marketing_plan_item_id': item['id']})
    assert thread.status_code == 201, thread.text
    assert thread.json()['campaign_id'] == campaign['campaign_id']
    assert thread.json()['marketing_plan_id'] == plan['id'] and thread.json()['messages'] == []
    other = client.post('/api/campaigns', json={'name': 'Other campaign', 'brief': 'Unrelated'}).json()
    assert client.post('/api/conversations', json={'title': 'Mismatch', 'campaign_id': other['id'], 'marketing_plan_item_id': item['id']}).status_code == 422
    occasion.source_revision = 'updated-source'; session.commit()
    changed = client.get('/api/calendar', params={**params, 'include_links': True}).json()
    assert changed['linked_items'][0]['source_changed'] is True
    saved = client.get(f"/api/marketing-plan-items/{item['id']}").json()
    assert client.patch(f"/api/marketing-plan-items/{item['id']}", json={**item_payload(saved), 'status': 'cancelled'}).status_code == 200
    assert client.get('/api/calendar', params={**params, 'include_links': True}).json()['linked_items'] == []


def test_overview_links_task_to_parent_when_campaign_is_in_later_month(client):
    plan = client.post('/api/marketing-plans', json={'name': 'Future launch', 'start_date': '2027-01-01', 'end_date': '2027-12-31'}).json()
    response = client.post(f"/api/marketing-plans/{plan['id']}/items?version={plan['version']}", json=dict(title='March launch', strategy='Review the offer', campaign_start='2027-03-10', campaign_end='2027-03-12', preparation_start='2027-02-01', status='planned', tasks=[{'title': 'Review in February', 'due_date': '2027-02-15'}]))
    assert response.status_code == 201, response.text
    result = client.get('/api/calendar', params=dict(start='2027-02-01', end='2027-02-28', types='task', state='SGR', include_links=True)).json()
    assert [entry['title'] for entry in result['entries']] == ['Review in February']
    assert result['linked_items'][0]['id'] == response.json()['id']


def test_official_import_is_idempotent_and_atomic(client, session, tmp_path):
    assert import_calendar(session) == 0
    before = len(list(session.scalars(select(CalendarOccasion))))
    (tmp_path/'invalid.json').write_text(json.dumps([{'title':'Invalid official holiday'}]))
    with pytest.raises(ValueError): import_calendar(session, tmp_path)
    assert len(list(session.scalars(select(CalendarOccasion)))) == before


def test_business_event_date_range_and_optimistic_conflict(client):
    body = dict(title='Store anniversary', start_date='2026-12-30', end_date='2027-01-02', description='Preorder preparation', archived=False)
    event = client.post('/api/calendar/business-events', json=body).json()
    response = client.patch(f"/api/calendar/business-events/{event['id']}", json={**body,'version':event['version'],'title':'Updated anniversary'})
    assert response.status_code == 200
    assert client.patch(f"/api/calendar/business-events/{event['id']}", json={**body,'version':event['version']}).status_code == 409
    assert client.post('/api/calendar/business-events', json={**body,'end_date':'2026-01-01'}).status_code == 422


def test_preferences_validation_and_stale_write(client):
    pref = client.get('/api/calendar/preferences').json()
    updated = client.put('/api/calendar/preferences', json={**pref,'states':['SWK','SGR'],'annual_budget':12000}).json()
    assert updated['version'] == 1
    assert client.put('/api/calendar/preferences', json=pref).status_code == 409
    assert client.put('/api/calendar/preferences', json={**updated,'states':['BAD']}).status_code == 422


def test_annual_plan_is_bounded_and_acceptance_is_idempotent(client, session):
    run = planned(client)
    assert 1 <= len(run['proposal']['items']) <= 24
    assert list(session.scalars(select(Campaign))) == []
    first, second = accept(client, run), accept(client, run)
    assert first['id'] == second['id'] and len(first['items']) == len(second['items'])
    assert all(i['status'] == 'planned' for i in first['items'])
    assert list(session.scalars(select(Campaign))) == []


def test_repeated_request_key_returns_same_run_and_rejects_different_input(client):
    payload = request_payload()
    first = client.post('/api/calendar/runs', json=payload).json()
    assert client.post('/api/calendar/runs', json=payload).json()['id'] == first['id']
    assert client.post('/api/calendar/runs', json={**payload,'instructions':'Different request'}).status_code == 409


def test_source_change_requires_regeneration_before_accept(client, session):
    run = planned(client)
    occasion_id = next(i['occasion_id'] for i in run['proposal']['items'] if i['occasion_id'])
    occasion = session.get(CalendarOccasion, occasion_id)
    occasion.source_revision = 'changed-official-revision'; session.commit()
    response = client.post(f"/api/calendar/runs/{run['id']}/accept", json={'name':'stale'})
    assert response.status_code == 409
    assert list(session.scalars(select(MarketingPlanItem))) == []


def test_failed_provider_retains_saved_calendar_and_logs_failure(client):
    class Broken(CalendarPlanner):
        def plan(self, context, sink=None): raise ValueError('Provider unavailable')
    app.dependency_overrides[get_calendar_planner] = lambda: Broken(provider=DemoProvider())
    run = client.post('/api/calendar/runs', json=request_payload()).json()
    response = client.post(f"/api/calendar/runs/{run['id']}/stream")
    assert json.loads(response.text.splitlines()[-1])['kind'] == 'error'
    saved = client.get(f"/api/calendar/runs/{run['id']}").json()
    assert saved['status'] == 'failed' and saved['error'].startswith('Planning failed.')
    assert saved['events'][-1]['phase'] == 'failed'
    assert client.post(f"/api/calendar/runs/{run['id']}/stream").status_code == 409


def test_campaign_conversion_is_idempotent_and_preserves_provenance(client):
    item = accept(client, planned(client))['items'][0]
    first = client.post(f"/api/marketing-plan-items/{item['id']}/campaign", json={'version':item['version']}).json()
    second = client.post(f"/api/marketing-plan-items/{item['id']}/campaign", json={'version':item['version']}).json()
    assert first['campaign_id'] == second['campaign_id']
    campaign = client.get(f"/api/campaigns/{first['campaign_id']}").json()
    assert campaign['status'] == 'draft' and not campaign['auto_approve_plan'] and not campaign['auto_approve_assets']
    assert campaign['source_event'] == item['source_snapshot']['title']
    assert item['campaign_start'] in campaign['brief']
    conversation = client.get(f"/api/conversations/{first['conversation_id']}").json()
    assert conversation['marketing_plan_item_id'] == item['id']
    assert client.get(f"/api/campaigns/{campaign['id']}/calendar").json()['id'] == item['id']


def test_calendar_campaign_uses_existing_gates_through_creative_approval(client):
    item = accept(client, planned(client))['items'][0]
    cid = client.post(f"/api/marketing-plan-items/{item['id']}/campaign", json={'version':item['version']}).json()['campaign_id']
    assert client.post(f'/api/campaigns/{cid}/generate').status_code == 409
    concepts = client.post(f'/api/campaigns/{cid}/plan').json()['concepts']
    assert client.post(f'/api/campaigns/{cid}/approve').status_code == 409
    for concept in concepts: assert client.post(f"/api/concepts/{concept['id']}/decision", json={'decision':'approved'}).status_code == 200
    assert client.post(f'/api/campaigns/{cid}/approve').status_code == 200
    assert client.post(f'/api/campaigns/{cid}/generate').status_code == 200
    rendered = client.post(f'/api/campaigns/{cid}/render')
    assert rendered.status_code == 200, rendered.text
    for asset in client.get(f'/api/campaigns/{cid}/assets').json(): assert client.post(f"/api/assets/{asset['id']}/approve").status_code == 200
    assert client.post(f'/api/campaigns/{cid}/assets/approve').status_code == 200
    assert client.get(f'/api/campaigns/{cid}').json()['status'] == 'ready_to_publish'
    video = client.get(f'/api/campaigns/{cid}/video-brief')
    assert video.status_code == 200, video.text
    assert all(len(scene['body']) <= 700 for scene in video.json()['storyboard'])
    assert 'Planning budget estimate' not in video.json()['storyboard'][-1]['body']


def test_item_edit_preserves_campaign_and_handles_stale_version(client):
    item = accept(client, planned(client))['items'][0]
    converted = client.post(f"/api/marketing-plan-items/{item['id']}/campaign", json={'version':item['version']}).json()
    saved = converted['item']; before = client.get(f"/api/campaigns/{converted['campaign_id']}").json()['brief']
    payload = {**item_payload(saved),'title':'Edited calendar title'}
    assert client.patch(f"/api/marketing-plan-items/{saved['id']}",json=payload).status_code == 200
    assert client.patch(f"/api/marketing-plan-items/{saved['id']}",json=payload).status_code == 409
    assert client.get(f"/api/campaigns/{converted['campaign_id']}").json()['brief'] == before


def test_task_reminder_can_be_completed_and_snoozed(client, session, monkeypatch):
    item = accept(client, planned(client))['items'][0]
    monkeypatch.setattr('app.marketing_calendar.today',lambda:date(2027,1,1))
    monkeypatch.setattr('app.api.calendar.today',lambda:date(2027,1,1))
    task = MarketingTask(item_id=item['id'],title='Check delivery cutoff',due_date=date(2027,1,1))
    session.add(task); session.commit()
    notice=next(n for n in client.get('/api/calendar/attention').json() if n['title']==task.title)
    assert client.post('/api/calendar/attention/dismiss',json={'key':notice['key'],'until':'2027-01-07'}).status_code == 200
    assert not any(n['key']==notice['key'] for n in client.get('/api/calendar/attention').json())
    assert client.get('/api/calendar/preferences').status_code == 200
    assert client.patch(f'/api/marketing-tasks/{task.id}',json={'version':task.version,'due_date':'2027-01-01','status':'done'}).status_code == 200


def test_chat_proposes_calendar_run_without_creating_campaign(client):
    strategist=StubStrategist(ChatTurn(reply='Prepare a reviewed annual roadmap',action=ChatAction.PLAN_CALENDAR,calendar_request=CalendarIntent(start_date=date(2027,1,1),end_date=date(2027,12,31))))
    app.dependency_overrides[get_marketing_chat]=lambda:strategist
    thread=client.post('/api/conversations',json={'title':'Annual strategy'}).json()
    response=client.post(f"/api/conversations/{thread['id']}/messages",json={'content':'Plan my next year'}).json()
    assert response['authorized']=='calendar' and response['calendar_run_id']
    assert response['campaign'] is None and response['message']['calendar_run_id']==response['calendar_run_id']
    assert strategist.calls[0]['calendar_context']['occasions']


def test_conversation_rejects_cross_plan_item_association(client):
    item=accept(client,planned(client))['items'][0]
    other=client.post('/api/marketing-plans',json={'name':'Other','start_date':'2027-01-01','end_date':'2027-12-31'}).json()
    assert client.post('/api/conversations',json={'marketing_plan_id':other['id'],'marketing_plan_item_id':item['id']}).status_code==422


def test_ai_unknown_occasion_and_invented_product_are_rejected(client, session):
    run=client.post('/api/calendar/runs',json=request_payload()).json()
    context=session.get(CalendarRun,run['id']).input
    planner=CalendarPlanner(provider=DemoProvider()); proposal=planner.plan(context)
    proposal.items[0].occasion_id=999999
    with pytest.raises(ValueError,match='unknown calendar'): planner.validate(proposal,context)
    proposal.items[0].occasion_id=None; proposal.items[0].products=['Imaginary product']
    with pytest.raises(ValueError,match='invented a product'): planner.validate(proposal,context)


def test_detailed_item_proposal_and_reschedule_relative_tasks(client):
    plan=accept(client,planned(client))
    target=next(i for i in plan['items'] if i['campaign_start'].startswith('2027-08'))
    detail=planned(client, operation='item',plan_id=plan['id'],item_id=target['id'])
    updated=accept(client,detail)
    item=next(i for i in updated['items'] if i['id']==target['id'])
    assert item['tasks'] and len(updated['items'])==len(plan['items'])
    from datetime import timedelta
    payload=item_payload(item)
    payload['campaign_start']=str(date.fromisoformat(item['campaign_start'])+timedelta(days=1))
    payload['campaign_end']=str(date.fromisoformat(item['campaign_end'])+timedelta(days=1))
    payload['preparation_start']=str(date.fromisoformat(item['preparation_start'])+timedelta(days=1))
    response=client.patch(f"/api/marketing-plan-items/{item['id']}",json=payload)
    assert response.status_code==200,response.text
    assert date.fromisoformat(response.json()['tasks'][0]['due_date'])==date.fromisoformat(item['tasks'][0]['due_date'])+timedelta(days=1)


def test_selected_state_can_plan_a_sarawak_only_occasion(client,session):
    occasion=session.scalar(select(CalendarOccasion).where(CalendarOccasion.title.contains('Gawai'),CalendarOccasion.start_date==date(2027,6,1)))
    run=planned(client,operation='item',occasion_id=occasion.id,states=['SWK'])
    assert run['proposal']['items'][0]['occasion_id']==occasion.id


def test_state_filter_respects_saved_marketing_plan_targets(client):
    accept(client,planned(client))
    query='/api/calendar?start=2027-01-01&end=2027-12-31&types=plan,task&state='
    assert client.get(query+'SGR').json()['entries']
    assert client.get(query+'SWK').json()['entries']==[]


def test_new_preparation_task_and_blackout_validation(client):
    item=accept(client,planned(client))['items'][0]
    response=client.post(f"/api/marketing-plan-items/{item['id']}/tasks",json={'title':'Confirm stock','due_date':item['campaign_start']})
    assert response.status_code==201 and response.json()['manual_date']
    assert client.post(f"/api/marketing-plan-items/{item['id']}/tasks",json={'title':'Out of range','due_date':'2029-01-01'}).status_code==422


def test_source_change_shows_difference_and_blocks_conversion(client,session):
    item=accept(client,planned(client))['items'][0]
    occasion=session.get(CalendarOccasion,item['occasion_id'])
    occasion.start_date=date(2027,1,2);occasion.end_date=date(2027,1,2);occasion.source_revision='corrected';session.commit()
    loaded=client.get(f"/api/marketing-plan-items/{item['id']}").json()
    assert loaded['source_changed'] and loaded['current_source_snapshot']['start_date']=='2027-01-02'
    assert client.post(f"/api/marketing-plan-items/{item['id']}/campaign",json={'version':item['version']}).status_code==409


def test_semantic_validation_repair_is_bounded(client,session):
    run=client.post('/api/calendar/runs',json=request_payload()).json()
    context=session.get(CalendarRun,run['id']).input
    class RepairingProvider(DemoProvider):
        calls=0
        def structured(self,**kwargs):
            self.calls+=1
            result=super().structured(**kwargs)
            if self.calls==1:result.items[0].occasion_id=999999
            return result
    provider=RepairingProvider();planner=CalendarPlanner(provider=provider)
    result=planner.plan(context)
    assert result.items and provider.calls==2 and planner.attempts==2


def test_interrupted_run_can_be_reopened_without_sticking_forever(client,session):
    from datetime import timedelta
    from app.clock import utcnow
    run=client.post('/api/calendar/runs',json=request_payload()).json()
    saved=session.get(CalendarRun,run['id']);saved.status='running';saved.updated_at=utcnow()-timedelta(minutes=16);session.commit()
    loaded=client.get(f"/api/calendar/runs/{run['id']}").json()
    assert loaded['status']=='interrupted' and loaded['error']
    assert any(item['id']==run['id'] for item in client.get('/api/calendar/runs').json())


def test_replanning_preserves_manual_dates_and_completed_tasks(client):
    plan=accept(client,planned(client))
    item=plan['items'][0]
    if not item['tasks']:
        plan=accept(client,planned(client,operation='item',plan_id=plan['id'],item_id=item['id']))
        item=plan['items'][0]
    first,second=item['tasks'][:2]
    from datetime import timedelta
    manual_date=str(date.fromisoformat(first['due_date'])+timedelta(days=1))
    assert client.patch(f"/api/marketing-tasks/{first['id']}",json={'version':first['version'],'due_date':manual_date,'status':'todo'}).status_code==200
    assert client.patch(f"/api/marketing-tasks/{second['id']}",json={'version':second['version'],'due_date':second['due_date'],'status':'done'}).status_code==200
    saved=accept(client,planned(client,operation='item',plan_id=plan['id'],item_id=item['id']))
    tasks={task['id']:task for task in saved['items'][0]['tasks']}
    assert len(tasks)==len(item['tasks'])
    assert tasks[first['id']]['due_date']==manual_date
    assert tasks[second['id']]['status']=='done'
