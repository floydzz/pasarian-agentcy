"""Calendar facts, reviewable AI proposals and ordinary campaign handoffs."""
from __future__ import annotations
import json
import time
from datetime import date, timedelta
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents.calendar_planner import CalendarPlanner
from app.agents.events import AgentEvent
from app.api.deps import _llm, get_store
from app.api.streaming import event_stream, ndjson
from app.calendar_schemas import (AcceptRequest, BusinessEventPatch, BusinessEventWrite, CalendarProposal,
    DateRange, DismissRequest, TaskProposal, ItemPatch, ItemWrite, PlanPatch, PlanWrite, Preferences, RunRequest, TaskPatch, VersionRequest)
from app.clock import utcnow
from app.db import get_db
from app.marketing_calendar import (add_item, as_dict, attention, calendar_entries, campaign_for_item,
    check_version, enforce_capacity, get_preferences, read_item, read_plan, record, run_context,
    save_preferences, today, validate_item, validate_context)
from app.models import (BusinessEvent, CalendarRun, MarketingPlan, MarketingPlanItem, MarketingPreference, MarketingTask)

router = APIRouter(prefix="/api", tags=["marketing calendar"])


def get_calendar_planner() -> CalendarPlanner:
    return CalendarPlanner(provider=_llm(), store=get_store())


@router.get("/calendar")
def read_calendar(start: date, end: date, state: str | None = None, types: str = "", include_links: bool = False, db: Session = Depends(get_db)):
    if end < start or (end-start).days > 400:
        raise HTTPException(422, "Choose an ordered date range of at most 400 days")
    selected = set(filter(None, types.split(',')))
    if selected - {"holiday", "school", "festival", "commercial", "business", "plan", "task", "none"}:
        raise HTTPException(422, "Unknown calendar entry type")
    return calendar_entries(db, start, end, state, selected, include_links=include_links)


@router.get("/calendar/preferences")
def preferences(db: Session = Depends(get_db)):
    return get_preferences(db)


@router.put("/calendar/preferences")
def update_preferences(payload: Preferences, db: Session = Depends(get_db)):
    try:
        return save_preferences(db, payload)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Preferences were saved in another tab. Reload and try again.") from error


@router.post("/calendar/business-events", status_code=201)
def create_business_event(payload: BusinessEventWrite, db: Session = Depends(get_db)):
    event = BusinessEvent(**payload.model_dump())
    db.add(event); db.commit()
    return as_dict(event)


@router.patch("/calendar/business-events/{event_id}")
def update_business_event(event_id: int, payload: BusinessEventPatch, db: Session = Depends(get_db)):
    event = record(db, BusinessEvent, event_id, lock=True)
    check_version(event, payload.version)
    for key, value in payload.model_dump(exclude={"version"}).items():
        setattr(event, key, value)
    event.version += 1; db.commit()
    return as_dict(event)


@router.get("/marketing-plans")
def list_plans(db: Session = Depends(get_db)):
    return [as_dict(plan) for plan in db.scalars(select(MarketingPlan).order_by(MarketingPlan.id.desc()))]


@router.post("/marketing-plans", status_code=201)
def create_plan(payload: PlanWrite, db: Session = Depends(get_db)):
    plan = MarketingPlan(**payload.model_dump(), constraints=get_preferences(db).model_dump(mode="json"))
    db.add(plan); db.commit()
    return read_plan(db, plan)


@router.get("/marketing-plans/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    return read_plan(db, record(db, MarketingPlan, plan_id))


@router.patch("/marketing-plans/{plan_id}")
def update_plan(plan_id: int, payload: PlanPatch, db: Session = Depends(get_db)):
    plan = record(db, MarketingPlan, plan_id, lock=True)
    check_version(plan, payload.version)
    items = list(db.scalars(select(MarketingPlanItem).where(MarketingPlanItem.plan_id == plan.id)))
    if any(i.campaign_start < payload.start_date or i.campaign_end > payload.end_date for i in items):
        raise HTTPException(422, "The new plan range would exclude existing items")
    for key, value in payload.model_dump(exclude={"version"}).items():
        setattr(plan, key, value)
    plan.version += 1; db.commit()
    return read_plan(db, plan)


@router.post("/marketing-plans/{plan_id}/items", status_code=201)
def create_item(plan_id: int, payload: ItemWrite, version: int = Query(ge=1), db: Session = Depends(get_db)):
    plan = record(db, MarketingPlan, plan_id, lock=True)
    check_version(plan, version)
    if plan.status == "archived":
        raise HTTPException(409, "This plan is archived")
    enforce_capacity(db, plan, [payload])
    item = add_item(db, plan, payload)
    plan.version += 1; db.commit()
    return read_item(db, item)


@router.get("/marketing-plan-items/{item_id}")
def get_item(item_id: int, db: Session = Depends(get_db)):
    return read_item(db, record(db, MarketingPlanItem, item_id))


@router.patch("/marketing-plan-items/{item_id}")
def update_item(item_id: int, payload: ItemPatch, db: Session = Depends(get_db)):
    # Lock parent first, consistently with proposal acceptance.
    initial = record(db, MarketingPlanItem, item_id)
    plan = record(db, MarketingPlan, initial.plan_id, lock=True)
    item = record(db, MarketingPlanItem, item_id, lock=True)
    check_version(item, payload.version)
    if plan.status == "archived":
        raise HTTPException(409, "This plan is archived")
    snapshot = validate_item(db, plan, payload, validate_tasks=False)
    if payload.status not in ("skipped", "cancelled"):
        enforce_capacity(db, plan, [payload], exclude_item_id=item.id)
    # Preserve completed/manual task history. Existing tasks are changed through their own endpoint.
    for task in db.scalars(select(MarketingTask).where(MarketingTask.item_id == item.id).with_for_update()):
        if task.status == "done":
            continue
        due = task.due_date if task.manual_date else max(payload.preparation_start, payload.campaign_start + timedelta(days=task.offset_days))
        if due < payload.preparation_start or due > payload.campaign_end:
            raise HTTPException(422, "A manually dated task falls outside the new period. Adjust that task before rescheduling.")
        if due != task.due_date:
            task.due_date = due; task.version += 1
    for key, value in payload.model_dump(exclude={"version", "tasks"}).items():
        setattr(item, key, value)
    item.source_snapshot = snapshot
    item.version += 1; plan.version += 1; db.commit()
    return read_item(db, item)


@router.post("/marketing-plan-items/{item_id}/campaign")
def create_item_campaign(item_id: int, payload: VersionRequest, db: Session = Depends(get_db)):
    return campaign_for_item(db, item_id, payload.version)


@router.get("/campaigns/{campaign_id}/calendar")
def campaign_calendar(campaign_id: int, db: Session = Depends(get_db)):
    from app.api.deps import get_campaign_or_404
    get_campaign_or_404(db, campaign_id)
    item = db.scalar(select(MarketingPlanItem).where(MarketingPlanItem.campaign_id == campaign_id))
    return read_item(db, item) if item else None


@router.post("/marketing-plan-items/{item_id}/tasks", status_code=201)
def create_task(item_id: int, payload: TaskProposal, db: Session = Depends(get_db)):
    item = record(db, MarketingPlanItem, item_id, lock=True)
    validate_context(db, item.plan_id, item.id)
    if not item.preparation_start <= payload.due_date <= item.campaign_end:
        raise HTTPException(422, "Task date must fall within preparation and campaign dates")
    count = len(list(db.scalars(select(MarketingTask.id).where(MarketingTask.item_id == item_id))))
    if count >= 30:
        raise HTTPException(422, "A campaign can have at most 30 preparation tasks")
    task = MarketingTask(item_id=item_id, title=payload.title, due_date=payload.due_date, offset_days=(payload.due_date-item.campaign_start).days, manual_date=True)
    db.add(task); db.commit()
    return as_dict(task)


@router.patch("/marketing-tasks/{task_id}")
def update_task(task_id: int, payload: TaskPatch, db: Session = Depends(get_db)):
    task = record(db, MarketingTask, task_id, lock=True)
    check_version(task, payload.version)
    item = record(db, MarketingPlanItem, task.item_id)
    validate_context(db, item.plan_id, item.id)
    if payload.due_date < item.preparation_start or payload.due_date > item.campaign_end:
        raise HTTPException(422, "Task date must fall within preparation and campaign dates")
    task.manual_date = task.manual_date or payload.due_date != task.due_date
    task.due_date, task.status = payload.due_date, payload.status
    task.version += 1; db.commit()
    return as_dict(task)


def create_run(db: Session, payload: RunRequest) -> CalendarRun:
    existing = db.scalar(select(CalendarRun).where(CalendarRun.request_key == payload.request_key))
    if existing:
        if RunRequest.model_validate(existing.input["request"]).model_dump(mode="json") != payload.model_dump(mode="json"):
            raise HTTPException(409, "This request key was already used for different planning inputs")
        return existing
    context = jsonable_encoder(run_context(db, payload))
    run = CalendarRun(request_key=payload.request_key, input=context)
    try:
        with db.begin_nested():
            db.add(run); db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(CalendarRun).where(CalendarRun.request_key == payload.request_key))
        if existing and RunRequest.model_validate(existing.input["request"]).model_dump(mode="json") == payload.model_dump(mode="json"):
            return existing
        raise HTTPException(409, "A planning request with this key already exists")
    return run


@router.post("/calendar/runs", status_code=201)
def new_run(payload: RunRequest, db: Session = Depends(get_db)):
    return as_dict(create_run(db, payload))


@router.get("/calendar/runs")
def list_calendar_runs(db: Session = Depends(get_db)):
    return [{"id": run.id, "status": run.status, "accepted": run.accepted, "created_at": run.created_at.isoformat() + "Z", "period": f"{run.input['request']['start_date']} to {run.input['request']['end_date']}"} for run in db.scalars(select(CalendarRun).order_by(CalendarRun.id.desc()).limit(20))]


@router.get("/calendar/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = record(db, CalendarRun, run_id)
    # Interrupted requests remain explicit, rather than presenting a permanent spinner.
    if run.status == "running" and run.updated_at < utcnow() - timedelta(minutes=15):
        run.status, run.error = "interrupted", "Planning was interrupted. Retry explicitly to prepare a new proposal."
        db.commit()
    return as_dict(run)


@router.post("/calendar/runs/{run_id}/stream")
def run_planning(run_id: int, db: Session = Depends(get_db), planner: CalendarPlanner = Depends(get_calendar_planner)):
    run = record(db, CalendarRun, run_id)
    if run.status == "succeeded":
        return StreamingResponse(iter([ndjson({"kind": "result", "run": jsonable_encoder(as_dict(run))})]), media_type="application/x-ndjson")
    claimed = db.execute(update(CalendarRun).where(CalendarRun.id == run_id, CalendarRun.status == "pending").values(status="running"))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "This request has already started. Reload its saved result or explicitly retry a failed request.")
    db.commit(); db.refresh(run)
    context, events, started = dict(run.input), [], time.monotonic()
    def work(sink):
        def report(event):
            events.append(event.as_dict()); sink(event)
        try:
            return planner.plan(context, sink=report)
        except Exception as error:
            report(AgentEvent("planner", "failed", str(error)))
            raise
    def finish(result):
        run.status, run.proposal = "succeeded", result.model_dump(mode="json")
        run.events, run.elapsed_ms = events, round((time.monotonic() - started) * 1000)
        run.usage = {"model": getattr(planner.provider, "model", "unknown"), "token_usage": None, "attempts": getattr(planner, "attempts", 1), "note": "Provider interface does not expose token usage"}
        db.commit()
        return {"run": jsonable_encoder(as_dict(run))}
    def recover():
        if not db.is_active:
            db.rollback()
        saved = record(db, CalendarRun, run_id)
        saved.status, saved.events = "failed", events
        saved.error = "Planning failed. Your saved calendar is unchanged. Review the saved job before retrying."
        saved.events = [{**event, "detail": "This step failed. Review saved output before retrying.", "data": {}} if event.get("phase") == "failed" else event for event in events]
        saved.elapsed_ms = round((time.monotonic() - started) * 1000)
        db.commit()
    return StreamingResponse(event_stream(work, finish, on_error=recover), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/calendar/runs/{run_id}/accept")
def accept_run(run_id: int, payload: AcceptRequest, db: Session = Depends(get_db)):
    run = record(db, CalendarRun, run_id, lock=True)
    if run.accepted:
        if not run.accepted_plan_id:
            raise HTTPException(409, "The accepted plan is no longer available")
        return read_plan(db, record(db, MarketingPlan, run.accepted_plan_id))
    if run.status != "succeeded" or not run.proposal:
        raise HTTPException(409, "Wait for a completed proposal before accepting it")
    request = RunRequest.model_validate(run.input["request"])
    current = jsonable_encoder(run_context(db, request))
    # Recheck authoritative inputs after provider latency and before applying the proposal.
    for key in ("preferences", "brand", "occasions", "business_events", "plan_version", "item_version"):
        if current[key] != run.input[key]:
            raise HTTPException(409, "Planning inputs changed. Review the current calendar and generate an updated proposal.")
    proposal = CalendarProposal.model_validate(run.proposal)
    try:
        CalendarPlanner.validate(proposal, current)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if current["plan_id"]:
        plan = record(db, MarketingPlan, current["plan_id"], lock=True)
        check_version(plan, payload.expected_version)
    else:
        plan = MarketingPlan(name=payload.name, start_date=request.start_date, end_date=request.end_date, goals=current["preferences"]["goals"], constraints=current["preferences"], status="accepted")
        db.add(plan); db.flush()
    enforce_capacity(db, plan, proposal.items, exclude_item_id=current["item_id"])
    if current["item_id"]:
        item = record(db, MarketingPlanItem, current["item_id"], lock=True)
        if item.campaign_id:
            raise HTTPException(409, "This item already has a production campaign. Edit the roadmap manually without overwriting its brief.")
        check_version(item, current["item_version"])
        drafted = proposal.items[0]
        snapshot = validate_item(db, plan, drafted)
        for key, value in drafted.model_dump(exclude={"tasks"}).items():
            setattr(item, key, value)
        item.source_snapshot, item.status = snapshot, "planned"
        item.version += 1
        existing_tasks = list(db.scalars(select(MarketingTask).where(MarketingTask.item_id == item.id).with_for_update()))
        by_title = {task.title.casefold(): task for task in existing_tasks}
        additions = [task for task in drafted.tasks if task.title.casefold() not in by_title]
        if len(existing_tasks) + len(additions) > 30:
            raise HTTPException(422, "This proposal would exceed 30 preparation tasks")
        proposed_titles = {task.title.casefold() for task in drafted.tasks}
        for task in existing_tasks:
            if task.status == "done":
                continue
            due = task.due_date
            if not task.manual_date and task.title.casefold() not in proposed_titles:
                due = max(drafted.preparation_start, drafted.campaign_start + timedelta(days=task.offset_days))
            if (task.manual_date or task.title.casefold() not in proposed_titles) and not drafted.preparation_start <= due <= drafted.campaign_end:
                raise HTTPException(409, "An existing task falls outside the proposed period. Adjust it before accepting this proposal.")
            if due != task.due_date:
                task.due_date = due; task.version += 1
        for proposed_task in drafted.tasks:
            task = by_title.get(proposed_task.title.casefold())
            if task is None:
                db.add(MarketingTask(item_id=item.id, title=proposed_task.title, due_date=proposed_task.due_date, offset_days=(proposed_task.due_date-item.campaign_start).days))
            elif task.status == "todo" and not task.manual_date:
                task.due_date = proposed_task.due_date
                task.offset_days = (task.due_date-item.campaign_start).days
                task.version += 1
    else:
        for drafted in proposal.items:
            add_item(db, plan, ItemWrite(**drafted.model_dump(), status="planned"))
    plan.version += 1
    run.accepted, run.accepted_plan_id = True, plan.id
    db.commit()
    return read_plan(db, plan)


@router.get("/calendar/attention")
def read_attention(db: Session = Depends(get_db)):
    return attention(db)


@router.post("/calendar/attention/dismiss")
def dismiss_attention(payload: DismissRequest, db: Session = Depends(get_db)):
    if not today() <= payload.until <= today() + timedelta(days=30):
        raise HTTPException(422, "Choose a snooze date within the next 30 days")
    if payload.key not in {item["key"] for item in attention(db)}:
        raise HTTPException(404, "This reminder no longer needs attention")
    from app.models import Workspace
    from app.workspace import workspace_id
    db.scalar(select(Workspace.id).where(Workspace.id == workspace_id()).with_for_update())
    row = db.scalar(select(MarketingPreference).with_for_update())
    if row is None:
        row = MarketingPreference( data=Preferences().model_dump(mode="json", exclude={"version"}), version=1)
        db.add(row)
    dismissed = {key: value for key, value in row.data.get("dismissed", {}).items() if value >= str(today())}
    if len(dismissed) >= 200:
        raise HTTPException(422, "Too many snoozed reminders. Wait for earlier snoozes to expire.")
    row.data = {**row.data, "dismissed": {**dismissed, payload.key: str(payload.until)}}
    db.commit()
    return {"status": "snoozed"}
