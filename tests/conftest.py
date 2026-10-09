import json
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def mock_http(monkeypatch):
    def install(handler):
        def post(url, **kwargs):
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                return client.post(url, **kwargs)

        monkeypatch.setattr(httpx, "post", post)

    return install


@pytest.fixture
def storefront():
    """Sanitized captures projected to the current GraphQL selections."""
    return json.loads((Path(__file__).parent / "fixtures" / "storefront.json").read_text())


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text("SHOPPY_USERNAME=test-user\nSHOPPY_PASSWORD=test-password\n")
    return path
