import pytest

from app.agents.chat import BriefDraft, ChatAction, ChatTurn, ConversationTurn, MarketingChat
from app.rag.store import KnowledgeStore
from tests.test_store import local_embedder


@pytest.fixture
def store(tmp_path):
    store = KnowledgeStore(path=tmp_path / "chroma", embedder=local_embedder)
    store.ingest_company_kb(
        "# Brand truth\nEmbun is a humidity-first hydrating serum. Never promise whitening.",
        source="brand.md",
    )
    store.ingest_trends(
        "# Trend signal\nShort humidity routines are rising on Malaysian TikTok.",
        source="trends.md",
    )
    return store


class Provider:
    def __init__(self, turn: ChatTurn):
        self.turn = turn
        self.calls: list[dict] = []

    def structured(self, *, system, prompt, schema):
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        return self.turn


def strategist(store, turn: ChatTurn):
    provider = Provider(turn)
    return MarketingChat(provider=provider, store=store), provider


def test_chat_keeps_company_and_trends_separate_in_its_prompt(store):
    agent, provider = strategist(
        store,
        ChatTurn(reply="A useful next question.", action=ChatAction.NONE),
    )

    agent.respond(
        "Launch our serum for humid weather.",
        history=[ConversationTurn(role="user", content="We want TikTok reach.")],
        campaign_name=None,
        campaign_status=None,
        campaign_brief=None,
        campaign_concepts=[],
    )

    prompt = provider.calls[0]["prompt"]
    assert "brand.md" in prompt and "trends.md" in prompt
    assert prompt.index("COMPANY KNOWLEDGE") < prompt.index("TREND SIGNALS")
    assert provider.calls[0]["schema"] is ChatTurn
    assert "ground truth" in provider.calls[0]["system"].lower()
    assert "inspiration only" in provider.calls[0]["system"].lower()


def test_chat_carries_history_and_the_campaign_state(store):
    agent, provider = strategist(
        store,
        ChatTurn(reply="I can plan this now.", action=ChatAction.RUN_PLAN),
    )

    turn = agent.respond(
        "Go ahead and plan it.",
        history=[ConversationTurn(role="assistant", content="The audience is founders.")],
        campaign_name="Serum launch",
        campaign_status="draft",
        campaign_brief="Launch Embun to founders in KL.",
        campaign_concepts=[],
    )

    assert turn.action is ChatAction.RUN_PLAN
    prompt = provider.calls[0]["prompt"]
    assert "ASSISTANT: The audience is founders." in prompt
    assert "Status: draft" in prompt
    assert "Launch Embun to founders in KL." in prompt
    assert prompt.index("LIVE CAMPAIGN STATE") > prompt.index("RECENT CONVERSATION")


def test_chat_supplies_a_safe_narration_for_an_action_only_provider_reply(store):
    agent, _ = strategist(store, ChatTurn(action=ChatAction.RUN_GENERATE))

    turn = agent.respond(
        "Generate the approved work.",
        history=[],
        campaign_name="Merdeka Skin Freedom",
        campaign_status="generating",
        campaign_brief="Launch the approved Merdeka bundle.",
        campaign_concepts=["The Great Unburdening"],
    )

    assert turn.action is ChatAction.RUN_GENERATE
    assert "starting the creative crew" in turn.reply


def test_chat_recovers_a_missing_draft_brief_from_the_marketers_request(store):
    agent, _ = strategist(
        store,
        ChatTurn(
            reply="I have prepared the campaign.",
            action=ChatAction.CREATE_CAMPAIGN,
            draft=BriefDraft(name="Merdeka luxury offer"),
        ),
    )
    request = "Promote our 31% Merdeka offer for five purchases or more."

    turn = agent.respond(
        request,
        history=[],
        campaign_name=None,
        campaign_status=None,
        campaign_brief=None,
        campaign_concepts=[],
    )

    assert turn.action is ChatAction.CREATE_CAMPAIGN
    assert turn.draft is not None
    assert turn.draft.brief == request


def test_chat_explains_the_asset_gate_when_a_provider_omits_its_reply(store):
    agent, _ = strategist(store, ChatTurn(action=ChatAction.NONE))

    turn = agent.respond(
        "What do you need from me?",
        history=[],
        campaign_name="Merdeka launch",
        campaign_status="pending_asset_review",
        campaign_brief="Launch the approved Merdeka campaign.",
        campaign_concepts=["Merdeka offer"],
    )

    assert turn.action is ChatAction.NONE
    assert "creative review" in turn.reply
    assert "approve" in turn.reply


def test_blank_chat_message_is_refused_before_retrieval(store):
    agent, _ = strategist(store, ChatTurn(reply="unused"))
    with pytest.raises(ValueError, match="message"):
        agent.respond(
            "  ",
            history=[],
            campaign_name=None,
            campaign_status=None,
            campaign_brief=None,
            campaign_concepts=[],
        )
