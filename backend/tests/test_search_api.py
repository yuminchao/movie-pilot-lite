from app.api.search import get_search_service
from app.integrations.mteam import IntegrationError, SearchResult
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
            poster_url="https://images.m-team.test/poster.jpg",
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
    assert body["items"][0]["poster_url"] == "https://images.m-team.test/poster.jpg"
    assert "secret" not in str(body).lower()


def test_search_rejects_unknown_category(client) -> None:
    _login(client)
    client.app.dependency_overrides[get_search_service] = lambda: SearchServiceStub()

    response = client.get(
        "/api/search",
        params={"q": "Movie", "category": "software"},
    )

    assert response.status_code == 422


def test_saved_mteam_settings_power_search(client, httpx_mock) -> None:
    _login(client)
    client.put(
        "/api/settings/mteam",
        json={
            "base_url": "https://m-team.test",
            "headers": {"x-api-key": "stored-secret"},
            "cookie": "tp=stored-cookie",
        },
    )
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/torrent/search",
        json={"data": {"data": []}},
    )

    response = client.get("/api/search", params={"q": "Movie"})

    assert response.status_code == 200
    request = httpx_mock.get_request()
    assert request.headers["x-api-key"] == "stored-secret"
    assert request.headers["Cookie"] == "tp=stored-cookie"


def test_integration_failure_returns_sanitized_bad_gateway(client) -> None:
    class FailingService:
        def search(self, keyword: str, category: str, page: int, sort: str):
            raise IntegrationError("M-Team 搜索失败")

    _login(client)
    client.app.dependency_overrides[get_search_service] = lambda: FailingService()

    response = client.get("/api/search", params={"q": "Movie"})

    assert response.status_code == 502
    assert response.json() == {"detail": "M-Team 搜索失败"}
