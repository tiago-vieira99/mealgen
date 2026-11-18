import os
import re
import tempfile

_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.name}"
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


class Client(TestClient):
    def csrf(self, path: str = "/login") -> str:
        return CSRF_RE.search(self.get(path).text).group(1)

    def submit(self, path: str, data: dict | list, csrf_from: str = "/login", **kwargs):
        token = self.csrf(csrf_from)
        pairs = list(data.items()) if isinstance(data, dict) else data
        form: dict[str, list[str]] = {"csrf_token": [token]}
        for key, value in pairs:
            form.setdefault(key, []).append(value)
        return self.post(path, data=form, **kwargs)


@pytest.fixture()
def client():
    with Client(app, follow_redirects=False) as c:
        yield c


_counter = iter(range(10_000))


@pytest.fixture()
def logged_in(client):
    username = f"user{next(_counter)}"
    r = client.submit("/register", {"username": username, "password": "password123", "password_confirm": "password123"})
    assert r.status_code == 303, r.text
    client.username = username
    return client
