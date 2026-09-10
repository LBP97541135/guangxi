import os

import pytest

os.environ.setdefault("MODEL_PROVIDER", "fake")

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        database_url="sqlite://",
        model_provider="fake",
    )


@pytest.fixture
def client(settings) -> TestClient:
    return TestClient(create_app(settings))
