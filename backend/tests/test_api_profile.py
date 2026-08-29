import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_store
from app.db import get_db
from app.main import app
from app.rag.store import COMPANY_KB, KnowledgeStore
from tests.test_store import local_embedder


@pytest.fixture
def store(tmp_path):
    return KnowledgeStore(path=tmp_path / "chroma", embedder=local_embedder)


@pytest.fixture
def client(session, store):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def profile_payload(**overrides):
    payload = {
        "company_name": "Kawan Kopi",
        "industry": "Specialty coffee",
        "website": "https://kawankopi.example",
        "description": "A Kuala Lumpur coffee roaster for people who brew at home.",
        "brand_voice": "Warm, curious, direct, never snobbish.",
        "target_audience": "Urban Malaysians aged 25–40 who care about better coffee.",
        "products": [
            {
                "name": "Rumah Blend",
                "description": "Chocolatey medium-roast coffee beans for espresso and milk drinks.",
                "price": "RM42 / 250g",
                "benefits": "Freshly roasted weekly; approachable for first-time home brewers.",
            }
        ],
        "approved_claims": "Freshly roasted weekly.",
        "restrictions": "Do not claim health benefits or use elitist coffee language.",
    }
    payload.update(overrides)
    return payload


def test_an_empty_workspace_reports_that_its_profile_is_not_configured(client):
    response = client.get("/api/brand-profile")

    assert response.status_code == 200
    assert response.json()["configured"] is False
    assert response.json()["products"] == []


def test_saving_a_profile_makes_it_the_only_company_ground_truth(client, store):
    store.ingest_company_kb("# Demo brand\n\nA demo serum.", source="products.md")

    response = client.put("/api/brand-profile", json=profile_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["company_name"] == "Kawan Kopi"
    assert body["knowledge_chunks"] >= 1
    assert [source.source for source in store.sources(COMPANY_KB)] == ["brand-profile.md"]
    retrieved = store.retrieve_company("Rumah Blend chocolatey coffee beans", k=10)
    assert any("Rumah Blend" in hit.text for hit in retrieved)


def test_saving_again_replaces_the_previous_profile(client, store):
    client.put("/api/brand-profile", json=profile_payload())
    response = client.put(
        "/api/brand-profile",
        json=profile_payload(company_name="Kawan Teh", products=[
            {"name": "Teh Bunga", "description": "A floral loose-leaf tea blend."}
        ]),
    )

    assert response.status_code == 200
    assert response.json()["company_name"] == "Kawan Teh"
    stored = store.retrieve_company("tea flower", k=4)
    assert stored and all("Rumah Blend" not in hit.text for hit in stored)


def test_a_product_needs_a_name_and_description(client):
    response = client.put(
        "/api/brand-profile",
        json=profile_payload(products=[{"name": "  ", "description": "  "}]),
    )

    assert response.status_code == 422
