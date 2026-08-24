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
                        "imageList": [
                            "http://images.m-team.test/insecure.jpg",
                            7,
                            "https://images.m-team.test/poster.jpg",
                            "https://images.m-team.test/second.jpg",
                        ],
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
    assert result.poster_url == "https://images.m-team.test/poster.jpg"
    request = httpx_mock.get_request()
    assert request.headers["x-api-key"] == "secret"
    assert request.headers["Cookie"] == "tp=secret"


@pytest.mark.parametrize(
    "image_list",
    [
        None,
        "https://images.m-team.test/poster.jpg",
        [],
        ["", None, 7, "http://images.m-team.test/insecure.jpg"],
    ],
)
def test_search_ignores_invalid_poster_lists(
    mteam_client: MTeamClient,
    httpx_mock,
    image_list,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/torrent/search",
        json={
            "data": {
                "data": [
                    {
                        "id": "7",
                        "name": "Movie",
                        "imageList": image_list,
                    }
                ]
            }
        },
    )

    result = mteam_client.search("Movie", "movie", 1)[0]

    assert result.poster_url is None


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


def test_get_download_url_posts_id_and_returns_response_data(
    mteam_client: MTeamClient,
    httpx_mock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.test/api/torrent/genDlToken?id=7",
        json={"data": "https://download.m-team.test/credential"},
    )

    url = mteam_client.get_download_url("7")

    assert url == "https://download.m-team.test/credential"
    assert httpx_mock.get_request().headers["x-api-key"] == "secret"


def test_mteam_site_subdomain_is_normalized_to_api_host(httpx_mock) -> None:
    client = MTeamClient(
        base_url="https://kp.m-team.cc",
        headers={"x-api-key": "secret"},
    )
    httpx_mock.add_response(
        method="POST",
        url="https://api.m-team.cc/api/torrent/search",
        json={"data": {"data": []}},
    )

    assert client.search("Movie", "all", 1) == []
