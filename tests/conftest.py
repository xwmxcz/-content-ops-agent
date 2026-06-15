import pytest

from src.utils import config


@pytest.fixture(autouse=True)
def disable_auth_by_default(monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", False)
