import pytest
from pydantic import ValidationError

from app.config import Settings


def test_health_returns_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_starts_without_model_key(settings):
    assert settings.model_api_key is None


def test_invalid_database_url_fails_settings():
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None, database_url="mysql://user:pass@host/db")

    assert "DATABASE_URL" in str(exc_info.value)


def test_invalid_provider_fails_settings():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, model_provider="chatgpt")
