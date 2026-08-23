from collections.abc import Iterator

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app(f"sqlite:///{tmp_path / 'test.db'}")) as test_client:
        yield test_client
