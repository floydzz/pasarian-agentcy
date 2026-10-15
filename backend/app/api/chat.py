"""Persistent marketing conversations and their deliberately narrow handoffs.

The chat agent proposes an action in structured output. This router is the
authority that persists it and decides whether the current campaign state may
actually start a streamed plan or generation run. It never crosses either
approval gate and never starts rendering.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from uuid import uuid4
from datetime import date, timedelta
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, selectinload, noload

from app.agents.chat import ChatAction, ConversationTurn, MarketingChat
from app.api.deps import Tuning, get_campaign_or_404, get_marketing_chat, get_tuning
from app.api.schemas import (
    CampaignRead,
    ChatMessageCreate,
    ChatMessageRead,
    ChatSendRead,
    ConversationCreate,
    ConversationPatch,
    ConversationRead,
)
from app.db import get_db
from app.domain import CampaignStatus, ConceptStatus
from app.models import Asset, Campaign, ChatMessage, Concept, Conversation, MarketingVideo, Variant

router = APIRouter(prefix="/api", tags=["chat"])


def _conversation_query():
    return select(Conversation).options(
        selectinload(Conversation.campaign),
        selectinload(Conversation.messages),
    )


def _read_conversation(db: Session, conversation_id: int) -> Conversation:
    conversation = db.scalar(
        _conversation_query().where(Conversation.id == conversation_id)
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no conversation {conversation_id}")
    return conversation


def _message_read(message: ChatMessage) -> ChatMessageRead:
    return ChatMessageRead.model_validate(message)


def _conversation_read(conversation: Conversation) -> ConversationRead:
    # SQLAlchemy does not promise relationship order without an explicit query.
    # Reading it in id order makes every API response and context window stable.
    conversation.messages.sort(key=lambda message: message.id)
    result = ConversationRead.model_validate(conversation)
    result.message_count = len(conversation.messages)
    return result


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(summary: bool = False, limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    query = select(Conversation).options(selectinload(Conversation.campaign), noload(Conversation.messages) if summary else selectinload(Conversation.messages)).order_by(Conversation.updated_at.desc(), Conversation.id.desc()).offset(offset).limit(limit)
    rows = list(db.scalars(query))
    if not summary:
        return [_conversation_read(row) for row in rows]
    counts = dict(db.execute(select(ChatMessage.conversation_id, func.count(ChatMessage.id)).where(ChatMessage.conversation_id.in_([row.id for row in rows])).group_by(ChatMessage.conversation_id)).all()) if rows else {}
    return [{**_conversation_read(row).model_dump(), "message_count": counts.get(row.id, 0)} for row in rows]


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate = Body(default_factory=ConversationCreate),
    db: Session = Depends(get_db),
) -> ConversationRead:
    if payload.campaign_id:
        get_campaign_or_404(db, payload.campaign_id)
    context = payload.model_dump(exclude={"title", "campaign_id"})
    context = _validate_calendar_context(db, context, payload.campaign_id)
    conversation = Conversation(title=payload.title, campaign_id=payload.campaign_id, **context)
    db.add(conversation)
    db.commit()
    return _conversation_read(_read_conversation(db, conversation.id))


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: int, db: Session = Depends(get_db)
) -> ConversationRead:
    from sqlalchemy.orm.attributes import set_committed_value
    row = db.scalar(select(Conversation).where(Conversation.id == conversation_id).options(selectinload(Conversation.campaign), noload(Conversation.messages)))
    if row is None:
        raise HTTPException(404, "Conversation not found")
    messages = list(db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == row.id).order_by(ChatMessage.id.desc()).limit(50)))
    set_committed_value(row, "messages", list(reversed(messages)))
    return _conversation_read(row)


@router.get("/conversations/{conversation_id}/messages")
def earlier_messages(conversation_id: int, before: int = Query(ge=1), db: Session = Depends(get_db)):
    if db.get(Conversation, conversation_id) is None:
        raise HTTPException(404, "Conversation not found")
    return [_message_read(row) for row in reversed(list(db.scalars(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id, ChatMessage.id < before).order_by(ChatMessage.id.desc()).limit(50))))]


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    conversation_id: int,
    payload: ConversationPatch,
    db: Session = Depends(get_db),
) -> ConversationRead:
    conversation = _read_conversation(db, conversation_id)
    if payload.title is not None:
        conversation.title = payload.title
    if "campaign_id" in payload.model_fields_set:
        if payload.campaign_id is None:
            conversation.campaign = None
        else:
            conversation.campaign = get_campaign_or_404(db, payload.campaign_id)
    for field in ("marketing_plan_id", "marketing_plan_item_id", "calendar_occasion_id", "calendar_business_event_id"):
        if field in payload.model_fields_set:
            setattr(conversation, field, getattr(payload, field))
    context = _validate_calendar_context(db, {field: getattr(conversation, field) for field in ("marketing_plan_id", "marketing_plan_item_id", "calendar_occasion_id", "calendar_business_event_id")}, conversation.campaign_id)
    for field, value in context.items():
        setattr(conversation, field, value)
    db.commit()
    return _conversation_read(_read_conversation(db, conversation_id))


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, db: Session = Depends(get_db)) -> None:
    conversation = _read_conversation(db, conversation_id)
    db.delete(conversation)
    db.commit()


@router.post("/conversations/{conversation_id}/messages", response_model=ChatSendRead)
def send_message(
    conversation_id: int,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    strategist: MarketingChat = Depends(get_marketing_chat),
    tuned: Tuning = Depends(get_tuning),
) -> ChatSendRead:
    conversation = _read_conversation(db, conversation_id)
    user_message = ChatMessage(
        conversation_id=conversation.id, role="user", content=payload.content
    )
    db.add(user_message)
    # The default title is only a placeholder. Giving the first real strategy
    # a short, meaningful name makes the thread picker usable without ever
    # changing a title the marketer deliberately wrote.
    if conversation.title == "New strategy":
        conversation.title = _thread_title(payload.content)
    db.flush()

    # The newly persisted line is passed separately as `message`, so history
    # ends at the prior turn. That avoids saying the same request twice.
    context_turns = tuned.value("chat", "context_turns")
    prior_messages = sorted(conversation.messages, key=lambda item: item.id)[-context_turns:]
    history = [
        ConversationTurn(role=message.role, content=message.content)
        for message in prior_messages
    ]
    campaign = conversation.campaign
    progress = _campaign_progress(db, campaign.id) if campaign else None

    try:
        turn = strategist.respond(
            payload.content,
            history=history,
            campaign_name=campaign.name if campaign else None,
            campaign_status=str(campaign.status) if campaign else None,
            campaign_brief=campaign.brief if campaign else None,
            campaign_concepts=[
                concept.theme
                for concept in campaign.concepts
                if concept.status is ConceptStatus.APPROVED
            ]
            if campaign
            else [],
            campaign_progress=progress,
            calendar_context=_calendar_context(db, conversation),
        )
    except Exception as error:
        # The user's request is still durable. A vendor refusal should read as
        # a machine status line, not erase their thought or leave a blank turn.
        system_message = ChatMessage(
            conversation_id=conversation.id,
            role="system",
            content=f"The strategist could not reply yet: {error}",
        )
        db.add(system_message)
        db.commit()
        db.refresh(system_message)
        return ChatSendRead(
            message=_message_read(system_message),
            campaign=CampaignRead.model_validate(conversation.campaign)
            if conversation.campaign
            else None,
        )

    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=turn.reply,
        action=turn.action.value if turn.action is not ChatAction.NONE else None,
    )
    db.add(assistant_message)
    db.flush()

    calendar_run_id = None
    if turn.action is ChatAction.PLAN_CALENDAR:
        from app.calendar_schemas import RunRequest
        from app.api.calendar import create_run
        if turn.calendar_request is None:
            _system(db, conversation, "Choose a planning period before preparing the calendar proposal.")
            authorized = "calendar"
        else:
            intent = turn.calendar_request
            try:
                request = RunRequest(
                    **intent.model_dump(), request_key=str(uuid4()),
                    states=_calendar_context(db, conversation).get("preferences", {}).get("states", []),
                    plan_id=conversation.marketing_plan_id, item_id=conversation.marketing_plan_item_id,
                    occasion_id=conversation.calendar_occasion_id if not conversation.marketing_plan_item_id else None,
                    business_event_id=conversation.calendar_business_event_id if not conversation.marketing_plan_item_id else None,
                )
                run = create_run(db, request)
                calendar_run_id = run.id
                assistant_message.calendar_run_id = run.id
                authorized = "calendar"
            except (HTTPException, ValueError) as error:
                _system(db, conversation, getattr(error, "detail", str(error)))
                authorized = "calendar"
    elif turn.action is ChatAction.VIEW_CALENDAR:
        authorized = "calendar"
    elif turn.action is ChatAction.CREATE_CAMPAIGN and conversation.marketing_plan_item_id:
        from app.marketing_calendar import campaign_for_item, record
        from app.models import MarketingPlanItem
        item = record(db, MarketingPlanItem, conversation.marketing_plan_item_id)
        try:
            result = campaign_for_item(db, item.id, item.version)
            conversation.campaign_id = result["campaign_id"]
            _system(db, conversation, "The calendar campaign is ready as a draft. Review its brief before planning concepts.")
        except HTTPException as error:
            _system(db, conversation, error.detail)
        authorized = None
    elif turn.action is ChatAction.CREATE_CAMPAIGN and conversation.marketing_plan_id and not conversation.campaign_id:
        _system(db, conversation, "Choose an item in this roadmap to create its campaign. Your annual strategy stays separate from production conversations.")
        authorized = "calendar"
    else:
        authorized = _execute_action(db, conversation, turn.action, turn.draft, message=payload.content)
    db.commit()
    db.refresh(assistant_message)
    # `conversation.campaign` may have changed during creation, and the return
    # carries it so the browser can immediately route the existing stream.
    campaign = conversation.campaign
    return ChatSendRead(
        message=_message_read(assistant_message),
        campaign=CampaignRead.model_validate(campaign) if campaign else None,
        authorized=authorized,
        calendar_run_id=calendar_run_id,
    )


def _execute_action(
    db: Session,
    conversation: Conversation,
    action: ChatAction,
    draft,
    *,
    message: str,
) -> str | None:
    """Validate the proposal against current persistence, never stale prompt state."""
    campaign = conversation.campaign
    if action is ChatAction.NONE:
        return None

    if action is ChatAction.CREATE_CAMPAIGN:
        if campaign is not None:
            _system(db, conversation, "A campaign is already attached to this strategy thread, so I kept the brief there.")
            return None
        # A valid model response can still omit the nested brief key. The
        # user's just-persisted request is the authoritative description for
        # this turn, so it is a safe recovery rather than an invented claim.
        if draft is not None and draft.name.strip() and not draft.brief.strip():
            draft.brief = message
        if draft is None or not draft.name.strip() or not draft.brief.strip():
            _system(db, conversation, "I need a campaign name and brief before I can create the campaign.")
            return None
        campaign = Campaign(name=draft.name, brief=draft.brief)
        db.add(campaign)
        db.flush()
        conversation.campaign = campaign
        _system(
            db,
            conversation,
            f"Campaign “{campaign.name}” is ready as a draft. Ask me to plan it when you want concepts.",
        )
        return None

    # This is a read-only showcase of a seed trailer, not a campaign stage.
    # It stays available before a campaign exists so the strategist can open
    # it during a standalone product demonstration as well.
    if action is ChatAction.OPEN_CINEMATIC_DEMO:
        return "cinematic"

    if campaign is None:
        _system(db, conversation, "There is no campaign attached yet, so I cannot start that stage.")
        return None

    if action is ChatAction.RUN_PLAN:
        if campaign.status is not CampaignStatus.DRAFT:
            _system(db, conversation, _wrong_stage(campaign, "plan"))
            return None
        return "plan"

    if action is ChatAction.RUN_GENERATE:
        if campaign.status is not CampaignStatus.GENERATING:
            _system(db, conversation, _wrong_stage(campaign, "generate"))
            return None
        # The existing generation route also enforces this rule; checking it
        # here prevents the browser from opening a stream that can only 409.
        approved = db.scalar(
            select(Concept.id)
            .where(Concept.campaign_id == campaign.id)
            .where(Concept.status == ConceptStatus.APPROVED)
            .limit(1)
        )
        if approved is None:
            _system(db, conversation, "The plan still needs at least one human-approved concept before generation can start.")
            return None
        return "generate"

    if action is ChatAction.RUN_RENDER:
        if campaign.status is not CampaignStatus.GENERATING:
            _system(db, conversation, _wrong_stage(campaign, "render images"))
            return None
        progress = _campaign_progress(db, campaign.id)
        if progress["variants"] == 0:
            _system(db, conversation, "The creative crew must finish the copy before Image Studio can render it.")
            return None
        if progress["assets"] > 0:
            _system(db, conversation, "Image creatives already exist. I opened their review workspace instead of generating duplicates.")
            return "image"
        return "render"

    if action is ChatAction.OPEN_IMAGE:
        return "image"

    if action is ChatAction.RUN_VIDEO:
        if campaign.status is not CampaignStatus.READY_TO_PUBLISH:
            _system(db, conversation, "Approve at least one image creative before producing the campaign video.")
            return None
        progress = _campaign_progress(db, campaign.id)
        if progress["videos"] > 0:
            _system(db, conversation, "A campaign video already exists. I opened Video Studio for review instead of rendering a duplicate.")
            return "video"
        return "video"

    if action is ChatAction.OPEN_VIDEO:
        return "video"

    if action is ChatAction.OPEN_PUBLISH:
        if campaign.status is not CampaignStatus.READY_TO_PUBLISH:
            _system(db, conversation, _wrong_stage(campaign, "prepare publishing"))
            return None
        progress = _campaign_progress(db, campaign.id)
        if progress["approved_assets"] == 0 and progress["approved_videos"] == 0:
            _system(db, conversation, "Approve an image or video before opening the publish package.")
            return None
        return "publish"

    return None


def _campaign_progress(db: Session, campaign_id: int) -> dict[str, int]:
    """Small authoritative counters for the strategist's scripted next step."""
    variants = list(
        db.scalars(
            select(Variant)
            .join(Concept, Variant.concept_id == Concept.id)
            .where(Concept.campaign_id == campaign_id)
        )
    )
    assets = list(
        db.scalars(
            select(Asset)
            .join(Variant, Asset.variant_id == Variant.id)
            .join(Concept, Variant.concept_id == Concept.id)
            .where(Concept.campaign_id == campaign_id)
        )
    )
    videos = list(
        db.scalars(select(MarketingVideo).where(MarketingVideo.campaign_id == campaign_id))
    )
    return {
        "variants": len(variants),
        "assets": len(assets),
        "approved_assets": sum(row.review_status == "approved" for row in assets),
        "videos": len(videos),
        "pending_videos": sum(row.review_status == "pending" for row in videos),
        "approved_videos": sum(row.review_status == "approved" for row in videos),
    }


def _thread_title(content: str) -> str:
    """A compact thread label from the first genuine request.

    It is deliberately deterministic rather than another model call: a title
    is navigation metadata, not copy worth spending a request on.
    """
    words = content.split()
    title = " ".join(words[:7]).strip()
    if len(words) > 7:
        title += "…"
    return title[:255] or "New strategy"


def _system(db: Session, conversation: Conversation, content: str) -> None:
    db.add(ChatMessage(conversation_id=conversation.id, role="system", content=content))


def _wrong_stage(campaign: Campaign, action: str) -> str:
    if campaign.status is CampaignStatus.PENDING_PLAN_APPROVAL:
        return "The concept gate is waiting for a human decision. I will not move past it."
    if campaign.status is CampaignStatus.PENDING_ASSET_REVIEW:
        return "The asset gate is waiting for a human decision. I will not move past it."
    return f"This campaign is {campaign.status}, so it is not ready to {action} yet."


def _validate_calendar_context(db, context, campaign_id=None):
    from app.marketing_calendar import validate_context, record
    from app.models import CalendarOccasion, BusinessEvent
    plan, item = validate_context(db, context.get("marketing_plan_id"), context.get("marketing_plan_item_id"), campaign_id)
    if item:
        if context.get("calendar_occasion_id") or context.get("calendar_business_event_id"):
            raise HTTPException(422, "An existing plan item already defines its occasion")
        context["marketing_plan_id"] = plan.id
    if context.get("calendar_occasion_id") and context.get("calendar_business_event_id"):
        raise HTTPException(422, "Select one occasion or business event")
    if context.get("calendar_occasion_id"):
        record(db, CalendarOccasion, context["calendar_occasion_id"])
    if context.get("calendar_business_event_id"):
        record(db, BusinessEvent, context["calendar_business_event_id"])
    return context


def _calendar_context(db, conversation):
    from app.calendar_schemas import RunRequest
    from app.marketing_calendar import run_context, record, today
    from app.models import MarketingPlan, CalendarOccasion, BusinessEvent
    now = today()
    start, end = now, now + timedelta(days=90)
    states = []
    if conversation.marketing_plan_id:
        plan = record(db, MarketingPlan, conversation.marketing_plan_id)
        start, end = plan.start_date, plan.end_date
    for model, identity in ((CalendarOccasion, conversation.calendar_occasion_id), (BusinessEvent, conversation.calendar_business_event_id)):
        if identity and not conversation.marketing_plan_id:
            selected = record(db, model, identity)
            if model is CalendarOccasion:
                from app.marketing_calendar import get_preferences
                preferred = get_preferences(db).states
                states = [s for s in preferred if s in selected.states] or selected.states[:1]
            start, end = date(selected.start_date.year, 1, 1), date(selected.start_date.year, 12, 31)
    try:
        context = run_context(db, RunRequest(states=states, start_date=start, end_date=end, plan_id=conversation.marketing_plan_id, item_id=conversation.marketing_plan_item_id, occasion_id=conversation.calendar_occasion_id if not conversation.marketing_plan_item_id else None, business_event_id=conversation.calendar_business_event_id if not conversation.marketing_plan_item_id else None, request_key="chat-context"))
        context["today"] = str(now)
        return jsonable_encoder(context)
    except HTTPException as error:
        return {"today": str(now), "context_error": error.detail}
