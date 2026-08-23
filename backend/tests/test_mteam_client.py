import json

import httpx
import pytest

from app.integrations.mteam import IntegrationError, MTeamClient


@pytest.fixture
def mteam_client() -> MTeamClient:
    return MTeamClient(
        base_url="https://m-team.test",
        headers={"x-api-key": "secret"},
        cookie="tp=secret",
        user_agent="movie-pilot-lite-test",
    )


def test_search_maps_movie_result(mteam_client: MTeamClient, httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/torrent/search",
        json={
            "data": {
                "data": [
                    {
                        "id": "7",
                        "name": "Movie",
                        "smallDescr": "description",
                        "category": "401",
                        "size": 1000,
                        "createdDate": "2026-08-23T10:00:00Z",
                        "status": {
                            "seeders": 8,
                            "leechers": 2,
                            "timesCompleted": 4,
                            "discount": "FREE",
                        },
                    }
                ]
            }
        },
    )

    result = mteam_client.search("Movie", "movie", 1)[0]

    assert result.title == "Movie"
    assert result.category == "movie"
    assert result.download_factor == 0
    assert result.seeders == 8
    request = httpx_mock.get_request()
    assert request.headers["x-api-key"] == "secret"
    assert request.headers["Cookie"] == "tp=secret"


def test_search_uses_tv_categories(mteam_client: MTeamClient, httpx_mock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/torrent/search",
        json={"data": {"data": []}},
    )

    mteam_client.search("Show", "tv", 2)

    request = httpx_mock.get_request()
    payload = json.loads(request.content)
    assert payload["pageNumber"] == 2
    assert payload["categories"] == ["403", "402", "435", "438", "404", "405"]


def test_non_success_response_raises_integration_error(
    mteam_client: MTeamClient,
    httpx_mock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/torrent/search",
        status_code=401,
    )

    with pytest.raises(IntegrationError, match="M-Team 搜索失败"):
        mteam_client.search("Movie", "all", 1)
