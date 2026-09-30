"""Content library search must run on full, tenant-scoped data before paging."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_store, get_system_store
from src.api.main import app
from src.models import ContentType, GeneratedContent
from src.storage.models import User


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _content(store, title="Article", body="Body", content_type=ContentType.XIAOHONGSHU, status="draft"):
    content_id = store.save_content(GeneratedContent(title=title, content=body, content_type=content_type))
    store.update_content(content_id, status=status, created_at=datetime(2026, 9, 1, 12, 0))
    return content_id


def test_search_matches_titles_and_full_content_case_insensitively(client, store):
    title_match = _content(store, title="Content SEARCH")
    body_match = _content(store, title=None, body="A" * 150 + " search in the full body")
    _content(store, title="Unrelated")

    response = client.get("/api/content", params={"q": "  SeArCh  "})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [body_match, title_match]
    # Preserve the list API's compact preview contract even for a full-body hit.
    assert response.json()[0]["content"] == "A" * 100 + "..."


def test_search_can_find_content_outside_the_first_default_page(client, store):
    wanted = _content(store, title="Needle")
    for index in range(51):
        _content(store, title=f"Newer {index}")

    assert wanted not in [item["id"] for item in client.get("/api/content").json()]
    response = client.get("/api/content", params={"q": "needle"})

    assert [item["id"] for item in response.json()] == [wanted]


@pytest.mark.parametrize(
    "needle,matching,unrelated",
    [
        ("%", "Save 20% today", "Save 20 percent today"),
        ("_", "release_v2", "release-v2"),
        ("/", "path/file", "path-file"),
        ("\\", "path\\file", "path-file"),
        ("/%_", "literal /%_ pattern", "literal /anyX pattern"),
        ("' OR 1=1 --", "literal ' OR 1=1 -- text", "Other content"),
    ],
)
def test_search_treats_like_wildcards_and_sql_syntax_as_literal_text(client, store, needle, matching, unrelated):
    wanted = _content(store, title=matching)
    _content(store, title=unrelated)

    response = client.get("/api/content", params={"q": needle})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [wanted]


def test_search_combines_filters_before_pagination_and_breaks_date_ties_by_id(client, store):
    first = _content(store, title="Topic one")
    _content(store, title="Topic blog", content_type=ContentType.BLOG)
    _content(store, title="Topic archived", status="archived")
    _content(store, title="Unrelated")
    second = _content(store, title="Topic two")
    third = _content(store, title="Topic three")
    params = {"q": "topic", "status": "draft", "content_type": "xiaohongshu", "limit": 2}

    first_page = client.get("/api/content", params={**params, "offset": 0}).json()
    second_page = client.get("/api/content", params={**params, "offset": 2}).json()

    assert [item["id"] for item in first_page] == [third, second]
    assert [item["id"] for item in second_page] == [first]
    assert client.get("/api/content", params={**params, "offset": 3}).json() == []


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_search_preserves_unfiltered_list_behavior(client, store, query):
    _content(store, title="First")
    _content(store, title="Second")

    assert client.get("/api/content", params={"q": query}).json() == client.get("/api/content").json()


def test_search_without_a_match_returns_an_empty_list(client, store):
    _content(store)

    response = client.get("/api/content", params={"q": "不存在的关键词"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_does_not_expose_another_workspaces_content(client, store):
    system = get_system_store()
    foreign_user = "99999999999999999999999999999999"
    with system._get_session() as session:
        session.add(User(id=foreign_user, username="search_other", password_hash="!", is_active=True))
        session.commit()
    _content(system.for_user(foreign_user), title="Shared keyword", body="Secret text")
    own = _content(store, title="Shared keyword")

    assert [item["id"] for item in client.get("/api/content", params={"q": "shared"}).json()] == [own]
    assert client.get("/api/content", params={"q": "Secret"}).json() == []
