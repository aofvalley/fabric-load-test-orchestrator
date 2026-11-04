import pytest

from helpers import install_fake_fabric_modules


@pytest.fixture
def fake_fabric(monkeypatch):
    install_fake_fabric_modules(monkeypatch)
