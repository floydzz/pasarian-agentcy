"""Persistent marketing conversations and their deliberately narrow handoffs.

The chat agent proposes an action in structured output. This router is the
authority that persists it and decides whether the current campaign state may
actually start a streamed plan or generation run. It never crosses either
approval gate and never starts rendering.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

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
from app.models import Campaign, ChatMessage, Concept, Conversation

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
    return ConversationRead.model_validate(conversation)


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(db: Session = Depends(get_db)) -> list[ConversationRead]:
    conversations = list(
        db.scalars(_conversation_query().order_by(Conversation.updated_at.desc(), Conversation.id.desc()))
    )
    return [_conversation_read(conversation) for conversation in conversations]


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreate = Body(default_factory=ConversationCreate),
    db: Session = Depends(get_db),
) -> ConversationRead:
    conversation = Conversation(title=payload.title)
    db.add(conversation)
    db.commit()
    return _conversation_read(_read_conversation(db, conversation.id))


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: int, db: Session = Depends(get_db)
) -> ConversationRead:
    return _conversation_read(_read_conversation(db, conversation_id))


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

    authorized = _execute_action(
        db, conversation, turn.action, turn.draft, message=payload.content
    )
    db.commit()
    db.refresh(assistant_message)
    # `conversation.campaign` may have changed during creation, and the return
    # carries it so the browser can immediately route the existing stream.
    campaign = conversation.campaign
    return ChatSendRead(
        message=_message_read(assistant_message),
        campaign=CampaignRead.model_validate(campaign) if campaign else None,
        authorized=authorized,
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

    return None


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
