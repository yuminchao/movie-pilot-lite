def test_health_returns_ok(client) -> None:
    response = client.get("/mpl/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

