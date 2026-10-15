"""Create a labelled offline calendar example once, without model/API charges."""
from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from app.agents.calendar_planner import CalendarPlanner
from app.api.calendar import create_run, accept_run
from app.calendar_schemas import AcceptRequest, RunRequest
from app.config import get_settings
from app.db import SessionLocal
from app.llm.demo import DemoProvider
from app.models import MarketingPlan

if __name__ == '__main__':
    settings = get_settings()
    if not settings.scripted_demo and settings.llm_provider != 'demo':
        raise SystemExit('Run this example explicitly in demo mode (LLM_PROVIDER=demo).')
    example = json.loads((Path(__file__).resolve().parents[1] / 'data/examples/calendar-demo.json').read_text())
    with SessionLocal() as db:
        if db.scalar(select(MarketingPlan).where(MarketingPlan.name == example['name'])):
            print('The calendar demo roadmap already exists.')
        else:
            request = RunRequest(**{key: example[key] for key in ('start_date','end_date','instructions')}, request_key='offline-calendar-demo-2027')
            run = create_run(db, request)
            if not run.proposal:
                proposal = CalendarPlanner(provider=DemoProvider()).plan(run.input)
                run.status, run.proposal = 'succeeded', proposal.model_dump(mode='json')
                db.commit()
            plan = accept_run(run.id, AcceptRequest(name=example['name']), db)
            print(f"Calendar demo roadmap {plan['id']} is ready; no model tokens used.")
