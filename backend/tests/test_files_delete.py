import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_store
from app.database.sqlite_store import SQLiteStore
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALFRED_DATA_DIR", str(tmp_path))
    store = SQLiteStore(tmp_path / "alfred.db")
    app.dependency_overrides[get_store] = lambda: store
    yield TestClient(app), tmp_path, store
    app.dependency_overrides.clear()


def _upload(c, name="notes.txt", body=b"the quick brown zebra jumps"):
    r = c.post("/api/files/upload", files={"file": (name, body, "text/plain")})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_delete_removes_file_record_chunks_and_search_hits(client):
    c, data_dir, store = client
    keep, drop = _upload(c, "keep.txt", b"alpha beta"), _upload(c)
    stored = list((data_dir / "uploads").glob(f"{drop}.*"))
    assert len(stored) == 1
    assert c.post("/api/files/search", json={"query": "zebra"}).json()["files"]

    assert c.delete(f"/api/files/{drop}").status_code == 204

    assert not list((data_dir / "uploads").glob(f"{drop}.*"))
    assert [f["id"] for f in c.get("/api/files").json()] == [keep]
    assert c.post("/api/files/search", json={"query": "zebra"}).json()["files"] == []
    assert (data_dir / "uploads" / next((data_dir / "uploads").iterdir()).name).exists()  # the other file is untouched


def test_delete_unknown_document_is_404(client):
    c, _, _ = client
    assert c.delete("/api/files/doesnotexist").status_code == 404
