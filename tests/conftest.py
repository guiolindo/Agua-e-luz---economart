import os
import tempfile

from cryptography.fernet import Fernet

_tmp = tempfile.mkdtemp()
os.environ.update(DEBUG="true", EXTRACTION_PROVIDER="mock", GEMINI_API_KEY="", ADMIN_USERNAME="admin",
                  ADMIN_PASSWORD="admin-pass-123", SECRET_KEY="test-secret",
                  DATABASE_URL=os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db", DOCUMENT_ENCRYPTION_KEY=Fernet.generate_key().decode())

import re  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import database  # noqa: E402
from app.main import app  # noqa: E402
from app.middleware import reset_rate_limits  # noqa: E402
from app.seed import seed  # noqa: E402

# PNG 1x1 válido (magic bytes corretos); o conteúdo não importa para o mock.
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63000100000005000100"
                    "5dcc2a6b0000000049454e44ae426082")


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    reset_rate_limits()
    yield


@pytest.fixture
def db():
    database.Base.metadata.drop_all(database.engine)
    database.Base.metadata.create_all(database.engine)
    session = database.SessionLocal()
    seed(session)
    try:
        yield session
    finally:
        session.close()


class Client:
    """TestClient com login e CSRF automáticos."""

    def __init__(self, tc: TestClient):
        self.tc = tc
        self.token = ""

    def refresh(self):
        html = self.tc.get("/login").text
        self.token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def login(self):
        self.refresh()
        r = self.tc.post("/login", data={"username": "admin", "password": "admin-pass-123", "csrf_token": self.token},
                         follow_redirects=False)
        assert r.status_code == 303
        self.refresh()

    def get(self, url, **kw):
        return self.tc.get(url, **kw)

    def post(self, url, data=None, **kw):
        return self.tc.post(url, data={**(data or {}), "csrf_token": self.token}, follow_redirects=False, **kw)


@pytest.fixture
def client():
    database.Base.metadata.drop_all(database.engine)
    with TestClient(app) as tc:
        c = Client(tc)
        c.login()
        yield c


@pytest.fixture
def png():
    return PNG
