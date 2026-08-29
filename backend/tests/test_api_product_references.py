import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.deps import get_storage
from app.db import get_db
from app.main import app
from app.media.storage import AssetStorage


def _product_data_url(colour: str = "crimson") -> str:
    image = Image.new("RGB", (400, 400), colour)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


@pytest.fixture
def storage(tmp_path):
    return AssetStorage(tmp_path)


@pytest.fixture
def client(session, storage):
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _campaign(client):
    return client.post(
        "/api/campaigns",
        json={"name": "Product launch", "brief": "Sell the real packshot."},
    ).json()


def test_campaign_product_library_selects_one_primary_and_promotes_on_delete(client, storage):
    campaign = _campaign(client)
    first = client.post(
        f"/api/campaigns/{campaign['id']}/product-references",
        json={"label": "Front pack", "data_url": _product_data_url()},
    )
    assert first.status_code == 201
    assert first.json()["is_primary"] is True
    assert storage.read(first.json()["media_url"])

    second = client.post(
        f"/api/campaigns/{campaign['id']}/product-references",
        json={
            "label": "Side pack",
            "data_url": _product_data_url("navy"),
            "is_primary": True,
        },
    )
    assert second.status_code == 201
    assert second.json()["is_primary"] is True

    rows = client.get(f"/api/campaigns/{campaign['id']}/product-references").json()
    assert [row["is_primary"] for row in rows] == [True, False]

    assert client.delete(
        f"/api/campaigns/{campaign['id']}/product-references/{second.json()['id']}"
    ).status_code == 204
    remaining = client.get(f"/api/campaigns/{campaign['id']}/product-references").json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == first.json()["id"]
    assert remaining[0]["label"] == "Front pack"
    assert remaining[0]["is_primary"] is True


def test_product_library_rejects_unsupported_files(client):
    campaign = _campaign(client)
    response = client.post(
        f"/api/campaigns/{campaign['id']}/product-references",
        json={"data_url": "data:image/gif;base64,R0lGODlhAQABAAAAACw="},
    )
    assert response.status_code == 422
