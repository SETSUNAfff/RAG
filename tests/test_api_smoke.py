from fastapi.testclient import TestClient

from main import app


# 不依赖 MySQL/Milvus 的框架冒烟测试。
def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_placeholder() -> None:
    client = TestClient(app)
    response = client.post("/api/v1/chat")
    assert response.status_code == 501


def test_chunk_routes_are_removed() -> None:
    client = TestClient(app)
    post_response = client.post("/api/v1/chunks", json={})
    patch_response = client.patch("/api/v1/chunks/1", json={})
    get_response = client.get("/api/v1/chunks/1")
    assert post_response.status_code == 404
    assert patch_response.status_code == 404
    assert get_response.status_code == 404


def test_document_upload_routes_are_registered() -> None:
    client = TestClient(app)
    assert client.post("/api/v1/documents/upload").status_code == 422
    assert client.post("/api/v1/documents/1/reindex").status_code == 422
