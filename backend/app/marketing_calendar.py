"""Single-workspace calendar operations. AI proposes; these operations own writes."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from datetime import UTC, datetime
from fastapi import HTTPException
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.performance import performance_context
from app.calendar_schemas import ItemWrite, Preferences, RunRequest, STATES
from app.models import (Asset, BrandProfile, BusinessEvent, CalendarOccasion, CalendarRun,
                        Campaign, Conversation, MarketingPlan, MarketingPlanItem,
                        MarketingPreference, MarketingTask)


def today() -> date:
    return datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).date()


def record(db: Session, model, identity: int, *, lock: bool = False):
    query = select(model).where(model.id == identity)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, f"{model.__tablename__} record {identity} was not found")
    return row


def check_version(row, expected: int | None) -> None:
    if expected != row.version:
        raise HTTPException(409, "This record changed in another tab. Reload it before saving your changes.")


def as_dict(row) -> dict:
    values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    return {key: value.replace(tzinfo=UTC) if isinstance(value, datetime) and value.tzinfo is None else value for key, value in values.items()}


def get_preferences(db: Session) -> Preferences:
    row = db.scalar(select(MarketingPreference).limit(1))
    return Preferences.model_validate({**{k: v for k, v in row.data.items() if k != "dismissed"}, "version": row.version}) if row else Preferences()


def save_preferences(db: Session, payload: Preferences) -> dict:
    from app.models import Workspace
    from app.workspace import workspace_id
    db.scalar(select(Workspace.id).where(Workspace.id == workspace_id()).with_for_update())
    row = db.scalar(select(MarketingPreference).with_for_update())
    if row:
        check_version(row, payload.version)
        row.data = {**row.data, **payload.model_dump(mode="json", exclude={"version"})}
        row.version += 1
    else:
        if payload.version != 0:
            raise HTTPException(409, "Planning preferences changed. Reload before saving.")
        row = MarketingPreference( data=payload.model_dump(mode="json", exclude={"version"}), version=1)
        db.add(row)
    db.commit()
    return get_preferences(db).model_dump(mode="json")


def validate_context(db: Session, plan_id: int | None, item_id: int | None, campaign_id: int | None = None):
    plan = record(db, MarketingPlan, plan_id) if plan_id else None
    item = record(db, MarketingPlanItem, item_id) if item_id else None
    if item:
        if plan and item.plan_id != plan.id:
            raise HTTPException(422, "The selected item belongs to a different marketing plan")
        plan = plan or record(db, MarketingPlan, item.plan_id)
        if campaign_id and item.campaign_id != campaign_id:
            raise HTTPException(422, "The calendar item does not belong to this campaign")
    if plan and plan.status == "archived":
        raise HTTPException(409, "This marketing plan is archived. Select an active plan.")
    return plan, item


def source_snapshot(db: Session, item) -> dict:
    if item.occasion_id:
        occasion = record(db, CalendarOccasion, item.occasion_id)
        if occasion.publication_status == "withdrawn":
            raise HTTPException(409, "This occasion was withdrawn. Choose another date or occasion.")
        return {key: str(getattr(occasion, key)) for key in ("title", "start_date", "end_date", "source_revision", "source_url", "publication_status")}
    if item.business_event_id:
        event = record(db, BusinessEvent, item.business_event_id)
        if event.archived:
            raise HTTPException(409, "This business event is archived")
        return {"title": event.title, "start_date": str(event.start_date), "end_date": str(event.end_date), "version": event.version}
    return {}


def validate_item(db: Session, plan: MarketingPlan, payload, *, validate_tasks: bool = True) -> dict:
    if payload.campaign_start < plan.start_date or payload.campaign_end > plan.end_date:
        raise HTTPException(422, "Campaign dates must fall within the marketing plan")
    if payload.preparation_start < payload.campaign_start - timedelta(days=90):
        raise HTTPException(422, "Preparation can start at most 90 days before the campaign")
    if validate_tasks and any(task.due_date < payload.preparation_start or task.due_date > payload.campaign_end for task in payload.tasks):
        raise HTTPException(422, "Preparation tasks must fall between preparation start and campaign end")
    profile = db.scalar(select(BrandProfile).limit(1))
    known_products = {p["name"] for p in profile.products} if profile else set()
    if any(name not in known_products for name in payload.products):
        raise HTTPException(422, "A suggested product is not in the saved brand profile")
    return source_snapshot(db, payload)


def enforce_capacity(db: Session, plan: MarketingPlan, items: list, *, exclude_item_id: int | None = None):
    preferences = get_preferences(db)
    existing = list(db.scalars(select(MarketingPlanItem).where(
        MarketingPlanItem.status.notin_(["skipped", "cancelled"]),
        MarketingPlanItem.campaign_end >= plan.start_date,
        MarketingPlanItem.campaign_start <= plan.end_date,
    )))
    existing = [item for item in existing if item.id != exclude_item_id]
    counts = Counter((item.campaign_start.year, item.campaign_start.month) for item in [*existing, *items])
    if any(count > preferences.campaigns_per_month for count in counts.values()):
        raise HTTPException(422, "This proposal exceeds your monthly campaign capacity. Adjust the proposal or planning preferences.")
    # The planning budget applies to this roadmap, including all proposed additions.
    plan_existing = [item for item in existing if item.plan_id == plan.id]
    known = [item.budget for item in [*plan_existing, *items] if item.budget is not None]
    if preferences.annual_budget is not None and sum(known) > preferences.annual_budget + .001:
        raise HTTPException(422, "This proposal exceeds the roadmap budget. Adjust it or update planning preferences.")
    if any(item.campaign_start <= blocked <= item.campaign_end for item in items for blocked in preferences.blackout_dates):
        raise HTTPException(422, "A campaign overlaps one of your blackout dates")


def add_item(db: Session, plan: MarketingPlan, payload: ItemWrite) -> MarketingPlanItem:
    snapshot = validate_item(db, plan, payload)
    item = MarketingPlanItem(plan_id=plan.id, source_snapshot=snapshot, **payload.model_dump(exclude={"tasks"}))
    db.add(item)
    db.flush()
    for task in payload.tasks:
        db.add(MarketingTask(item_id=item.id, title=task.title, due_date=task.due_date, offset_days=(task.due_date - item.campaign_start).days))
    return item


def read_item(db: Session, item: MarketingPlanItem) -> dict:
    result = as_dict(item)
    result["tasks"] = [as_dict(task) for task in db.scalars(select(MarketingTask).where(MarketingTask.item_id == item.id).order_by(MarketingTask.due_date, MarketingTask.id))]
    campaign = db.get(Campaign, item.campaign_id) if item.campaign_id else None
    result["campaign_status"] = str(campaign.status) if campaign else None
    parent = db.get(MarketingPlan, item.plan_id)
    result["target_states"] = parent.constraints.get("states", []) if parent else []
    result["source_changed"] = source_changed(db, item)
    try:
        result["current_source_snapshot"] = source_snapshot(db, item)
    except HTTPException:
        result["current_source_snapshot"] = {"publication_status": "withdrawn"}
    return result


def source_changed(db: Session, item: MarketingPlanItem) -> bool:
    try:
        return source_snapshot(db, item) != item.source_snapshot
    except HTTPException:
        return True


def read_plan(db: Session, plan: MarketingPlan) -> dict:
    return {**as_dict(plan), "items": [read_item(db, item) for item in db.scalars(select(MarketingPlanItem).where(MarketingPlanItem.plan_id == plan.id).order_by(MarketingPlanItem.campaign_start, MarketingPlanItem.id))]}


def campaign_for_item(db: Session, item_id: int, version: int) -> dict:
    item = record(db, MarketingPlanItem, item_id, lock=True)
    # Idempotent across retries and concurrent requests, even with an old version.
    if item.campaign_id:
        conversation = db.scalar(select(Conversation).where(Conversation.campaign_id == item.campaign_id).order_by(Conversation.id))
        return {"campaign_id": item.campaign_id, "conversation_id": conversation.id if conversation else None, "item": read_item(db, item)}
    check_version(item, version)
    if item.status != "planned":
        raise HTTPException(409, "Accept this calendar item before creating a campaign")
    plan = record(db, MarketingPlan, item.plan_id)
    if plan.status == "archived":
        raise HTTPException(409, "This plan is archived")
    if source_changed(db, item):
        raise HTTPException(409, "The occasion changed. Review and save the item before creating its campaign.")
    snapshot = as_dict(item)
    snapshot = {key: str(value) if isinstance(value, (date, datetime)) else value for key, value in snapshot.items()}
    brief = "\n".join([
        item.strategy, f"Goal: {plan.goals or 'Use the saved brand goals'}", f"Audience: {item.audience or 'Saved brand audience'}",
        f"Products: {', '.join(item.products) or 'Select from the saved brand profile; do not invent a product'}",
        f"Campaign period: {item.campaign_start} to {item.campaign_end} (Asia/Kuala_Lumpur)",
        f"Preparation begins: {item.preparation_start}", f"Proposed offer, pending business confirmation: {item.offer or 'No discount or offer confirmed'}",
        f"Planning budget estimate: {'MYR ' + str(item.budget) if item.budget is not None else 'Not provided'}",
        f"Why this occasion: {item.rationale}", "Respect saved brand restrictions. Do not claim stock, delivery guarantees or offers are confirmed.",
    ])
    campaign = Campaign(name=item.title, brief=brief, source_event=item.source_snapshot.get("title"))
    db.add(campaign)
    db.flush()
    item.campaign_id = campaign.id
    item.campaign_snapshot = snapshot
    item.version += 1
    conversation = Conversation(title=item.title, campaign_id=campaign.id, marketing_plan_id=plan.id, marketing_plan_item_id=item.id)
    db.add(conversation)
    db.commit()
    return {"campaign_id": campaign.id, "conversation_id": conversation.id, "item": read_item(db, item)}


def run_context(db: Session, payload: RunRequest) -> dict:
    preferences = get_preferences(db)
    if payload.states:
        preferences.states = payload.states
    plan, item = validate_context(db, payload.plan_id, payload.item_id)
    if plan and not payload.states:
        preferences.states = plan.constraints.get("states", preferences.states)
    if item and (payload.occasion_id or payload.business_event_id):
        raise HTTPException(422, "An existing item already defines its occasion")
    if plan and (payload.start_date != plan.start_date or payload.end_date != plan.end_date):
        raise HTTPException(422, "Use the existing plan's date range")
    occasions = list(db.scalars(select(CalendarOccasion).where(
        CalendarOccasion.start_date <= payload.end_date, CalendarOccasion.end_date >= payload.start_date,
        CalendarOccasion.publication_status != "withdrawn",
    ).order_by(CalendarOccasion.start_date, CalendarOccasion.id)))
    occasions = [o for o in occasions if set(o.states) & set(preferences.states)]
    events = list(db.scalars(select(BusinessEvent).where(BusinessEvent.archived.is_(False), BusinessEvent.start_date <= payload.end_date, BusinessEvent.end_date >= payload.start_date).order_by(BusinessEvent.start_date)))
    selected_occasion = payload.occasion_id or (item.occasion_id if item else None)
    selected_event = payload.business_event_id or (item.business_event_id if item else None)
    if selected_occasion and not any(o.id == selected_occasion for o in occasions):
        raise HTTPException(422, "The selected occasion does not match the planning dates or selected states")
    if selected_event and not any(e.id == selected_event for e in events):
        raise HTTPException(422, "The selected business event is outside the planning range or archived")
    profile = db.scalar(select(BrandProfile).limit(1))
    brand = {key: getattr(profile, key) for key in ("company_name", "industry", "description", "target_audience", "products", "brand_voice", "approved_claims", "restrictions")} if profile else None
    existing = list(db.scalars(select(MarketingPlanItem).where(MarketingPlanItem.campaign_end >= payload.start_date, MarketingPlanItem.campaign_start <= payload.end_date, MarketingPlanItem.status.notin_(["skipped", "cancelled"]))))
    if len(existing) > 200:
        raise HTTPException(422, "Too many active items in this period. Archive unused roadmaps before generating another proposal.")
    return {
        "today": str(today()), "request": payload.model_dump(mode="json"), "preferences": preferences.model_dump(mode="json"), "brand": brand,
        "plan_version": plan.version if plan else None, "item_version": item.version if item else None,
        "plan_id": plan.id if plan else None, "item_id": item.id if item else None,
        "selected_occasion_id": selected_occasion, "selected_business_event_id": selected_event,
        "occasions": [{key: str(getattr(o, key)) if isinstance(getattr(o, key), date) else getattr(o, key) for key in ("id", "title", "start_date", "end_date", "states", "category", "source_revision", "publication_status")} for o in occasions],
        "business_events": [{"id": e.id, "title": e.title, "start_date": str(e.start_date), "end_date": str(e.end_date), "version": e.version} for e in events],
        "measured_performance": performance_context(db),
        "recent_campaigns": [{"id": c.id, "name": c.name, "brief": c.brief[:600], "status": str(c.status), "source_event": c.source_event, "scheduled_dates": "unknown unless linked to a calendar item"} for c in db.scalars(select(Campaign).order_by(Campaign.id.desc()).limit(30))],
        "existing_items": [{"id": i.id, "title": i.title, "campaign_start": str(i.campaign_start), "budget": i.budget} for i in existing],
        "selected_item": read_item(db, item) if item else None,
    }


def attention(db: Session) -> list[dict]:
    now = today()
    preferences = get_preferences(db)
    active = list(db.scalars(select(MarketingPlanItem).join(MarketingPlan).where(MarketingPlan.status != "archived", MarketingPlanItem.status.notin_(["skipped", "cancelled"]))))
    results = []
    for item in active:
        url = f"/calendar?item={item.id}"
        if source_changed(db, item):
            results.append({"key": f"source:{item.id}:{item.version}:{source_snapshot_safe(db, item)}", "title": f"Review changed dates for {item.title}", "kind": "source", "url": url, "action": "Review timing"})
        if item.campaign_end < now:
            continue
        if not item.campaign_id and item.status == "planned" and item.preparation_start <= now + timedelta(days=preferences.reminder_days):
            results.append({"key": f"prepare:{item.id}:{item.version}", "title": f"Preparation is due for {item.title}", "kind": "preparation", "url": url, "action": "Prepare campaign"})
        campaign = db.get(Campaign, item.campaign_id) if item.campaign_id else None
        if campaign and item.campaign_start <= now + timedelta(days=preferences.reminder_days) and str(campaign.status) not in ("ready_to_publish", "published"):
            results.append({"key": f"review:{item.id}:{campaign.status}:{item.version}", "title": f"{item.title} needs work before its start date", "kind": "readiness", "url": f"/campaigns/{campaign.id}", "action": "Open campaign"})
        for task in db.scalars(select(MarketingTask).where(MarketingTask.item_id == item.id, MarketingTask.status == "todo", MarketingTask.due_date <= now + timedelta(days=preferences.reminder_days))):
            results.append({"key": f"task:{task.id}:{task.version}", "title": task.title, "kind": "overdue" if task.due_date < now else "task", "due_date": str(task.due_date), "url": url, "action": "Review task"})
    counts = Counter((i.campaign_start.year, i.campaign_start.month) for i in active)
    for month, count in counts.items():
        if count > preferences.campaigns_per_month:
            results.append({"key": f"capacity:{month}:{count}:{preferences.version}", "title": f"{month[0]}-{month[1]:02d} exceeds your campaign capacity", "kind": "capacity", "url": "/calendar", "action": "Review plans"})
    for plan in db.scalars(select(MarketingPlan).where(MarketingPlan.status != "archived")):
        total = sum(i.budget or 0 for i in active if i.plan_id == plan.id)
        if preferences.annual_budget is not None and total > preferences.annual_budget:
            results.append({"key": f"budget:{plan.id}:{total}:{preferences.version}", "title": f"{plan.name} exceeds your planning budget", "kind": "budget", "url": f"/calendar?plan={plan.id}", "action": "Review budget"})
    row = db.scalar(select(MarketingPreference).limit(1))
    dismissed = row.data.get("dismissed", {}) if row else {}
    return [r for r in results if dismissed.get(r["key"], "") <= str(now)][:100]


def source_snapshot_safe(db: Session, item) -> str:
    import hashlib
    import json
    try:
        snapshot = source_snapshot(db, item)
    except HTTPException:
        snapshot = {"withdrawn": True}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:12]


def calendar_entries(db: Session, start: date, end: date, state: str | None, types: set[str], *, include_links: bool = False) -> dict:
    if state and state not in STATES:
        raise HTTPException(422, "Unknown Malaysian state")
    entries = []
    occasions = list(db.scalars(select(CalendarOccasion).where(CalendarOccasion.start_date <= end, CalendarOccasion.end_date >= start).order_by(CalendarOccasion.start_date)))
    for o in occasions:
        if state and state not in o.states:
            continue
        if not types or o.category in types:
            entries.append({"id": f"occasion:{o.id}", "entity_id": o.id, "kind": o.category, "title": o.title, "start_date": o.start_date, "end_date": o.end_date, "details": as_dict(o)})
    if not types or "business" in types:
        for e in db.scalars(select(BusinessEvent).where(BusinessEvent.archived.is_(False), BusinessEvent.start_date <= end, BusinessEvent.end_date >= start)):
            entries.append({"id": f"business:{e.id}", "entity_id": e.id, "kind": "business", "title": e.title, "start_date": e.start_date, "end_date": e.end_date, "details": as_dict(e)})
    items = list(db.scalars(select(MarketingPlanItem).join(MarketingPlan).where(MarketingPlan.status != "archived", MarketingPlanItem.status.notin_(["skipped", "cancelled"]), MarketingPlanItem.campaign_start <= end, MarketingPlanItem.campaign_end >= start)))
    parent_states = {p.id: p.constraints.get("states", []) for p in db.scalars(select(MarketingPlan).where(MarketingPlan.id.in_({item.plan_id for item in items})))}
    items = [item for item in items if not state or not parent_states[item.plan_id] or state in parent_states[item.plan_id]]
    if not types or "plan" in types:
        for item in items:
            entries.append({"id": f"plan:{item.id}", "entity_id": item.id, "kind": "plan", "title": item.title, "start_date": item.campaign_start, "end_date": item.campaign_end, "details": read_item(db, item)})
    if not types or "task" in types:
        tasks = db.execute(select(MarketingTask, MarketingPlanItem, MarketingPlan).join(MarketingPlanItem, MarketingTask.item_id == MarketingPlanItem.id).join(MarketingPlan).where(MarketingPlan.status != "archived", MarketingPlanItem.status.notin_(["skipped", "cancelled"]), MarketingTask.due_date.between(start, end))).all()
        for task, item, parent in tasks:
            if state and parent.constraints.get("states") and state not in parent.constraints["states"]:
                continue
            entries.append({"id": f"task:{task.id}", "entity_id": item.id, "kind": "task", "title": task.title, "start_date": task.due_date, "end_date": task.due_date, "details": {**as_dict(task), "item_title": item.title}})
    all_occasions = list(db.scalars(select(CalendarOccasion)))
    coverage = {str(year): {"categories": sorted({o.category for o in all_occasions if o.start_date.year == year}), "note": "Published dates; observed replacements and ad hoc declarations may require later updates."} for year in range(start.year, end.year + 1)}
    if len(entries) > 2000:
        raise HTTPException(422, "Too many entries. Select a shorter range or filter event types.")
    result = {"entries": entries, "coverage": coverage, "states": STATES, "timezone": "Asia/Kuala_Lumpur"}
    if include_links:
        # An occasion can have a campaign scheduled before the displayed month.
        # Resolve its active workspace-owned items by source identity, not dates
        # or title matching. Include task parents even when their launch is later.
        occasions = {e["entity_id"] for e in entries if e["kind"] not in {"business", "plan", "task"}}
        businesses = {e["entity_id"] for e in entries if e["kind"] == "business"}
        parents = {e["entity_id"] for e in entries if e["kind"] in {"plan", "task"}}
        linked = db.execute(select(MarketingPlanItem, Campaign.status, MarketingPlan.constraints)
            .join(MarketingPlan).outerjoin(Campaign, Campaign.id == MarketingPlanItem.campaign_id)
            .where(MarketingPlan.status != "archived", MarketingPlanItem.status.notin_(["skipped", "cancelled"]),
                   or_(MarketingPlanItem.occasion_id.in_(occasions), MarketingPlanItem.business_event_id.in_(businesses), MarketingPlanItem.id.in_(parents)))
            .order_by(MarketingPlanItem.campaign_start, MarketingPlanItem.id)).all()
        result["linked_items"] = []
        for item, campaign_status, constraints in linked:
            if state and constraints.get("states") and state not in constraints["states"]:
                continue
            if len(result["linked_items"]) >= 200:
                raise HTTPException(422, "Too many linked campaign ideas. Select a shorter calendar period.")
            result["linked_items"].append({key: getattr(item, key) for key in (
                "id", "plan_id", "title", "occasion_id", "business_event_id", "campaign_id", "status",
                "campaign_start", "campaign_end", "preparation_start")})
            result["linked_items"][-1].update(campaign_status=str(campaign_status) if campaign_status else None, source_changed=source_changed(db, item))
    return result
