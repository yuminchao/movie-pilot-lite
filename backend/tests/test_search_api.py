from app.api.search import get_search_service
from app.integrations.mteam import SearchResult
from app.services.search import SearchPage


class SearchServiceStub:
    def search(self, keyword: str, category: str, page: int, sort: str) -> SearchPage:
        assert (keyword, category, page, sort) == ("Movie", "movie", 1, "promotion")
        result = SearchResult(
            source_id="7",
            title="Movie",
            description="description",
            category="movie",
            size=1000,
            seeders=8,
            leechers=2,
            downloads=4,
            download_factor=0,
            upload_factor=1,
            created_at="2026-08-23T10:00:00Z",
            page_url="https://m-team.test/detail/7",
            labels=("中字",),
        )
        return SearchPage.from_results([result], page=1, token_factory=lambda _: "source-token")


def _login(client) -> None:
    client.post("/api/auth/setup", json={"password": "correct horse battery"})
    response = client.post("/api/auth/login", json={"password": "correct horse battery"})
    assert response.status_code == 204


def test_search_requires_session(client) -> None:
    response = client.get("/api/search", params={"q": "Movie"})

    assert response.status_code == 401


def test_search_returns_normalized_page_without_credentials(client) -> None:
    _login(client)
    client.app.dependency_overrides[get_search_service] = lambda: SearchServiceStub()

    response = client.get(
        "/api/search",
        params={
            "q": "Movie",
            "category": "movie",
            "page": 1,
            "sort": "promotion",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["items"][0]["title"] == "Movie"
    assert body["items"][0]["source_token"] == "source-token"
    assert "secret" not in str(body).lower()


def test_search_rejects_unknown_category(client) -> None:
    _login(client)
    client.app.dependency_overrides[get_search_service] = lambda: SearchServiceStub()

    response = client.get(
        "/api/search",
        params={"q": "Movie", "category": "software"},
    )

    assert response.status_code == 422
