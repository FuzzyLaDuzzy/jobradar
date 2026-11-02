import sys
from pathlib import Path

import httpx
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def portuguese():
    """The language is one global (jobradar.i18n): every test starts and ends in Portuguese."""
    from jobradar import i18n

    i18n.language = "pt"
    yield
    i18n.language = "pt"


@pytest.fixture
def cfg():
    return yaml.safe_load((ROOT / "config.example.yaml").read_text(encoding="utf-8"))


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def make_client():
    return mock_client
