import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from main import app

SCHEMA = app.openapi()


def matches(template: str, path: str) -> bool:
    pieces, parts = template.split("/"), path.split("/")
    return len(pieces) == len(parts) and all(
        piece == part or piece.startswith("{") for piece, part in zip(pieces, parts)
    )


def route_path(method: str, path: str) -> str | None:
    for template, operations in SCHEMA["paths"].items():
        if method.lower() in operations and matches(template, path):
            return template
    return None


def documented_codes(method: str, path: str, status_code: int) -> set[str]:
    responses = SCHEMA["paths"][path][method.lower()]["responses"]
    if str(status_code) not in responses:
        return set()
    body = responses[str(status_code)]["content"]["application/json"]["schema"]
    schemas = SCHEMA["components"]["schemas"]
    return {
        schemas[option["$ref"].rsplit("/", 1)[1]]["properties"]["code"]["const"]
        for option in body.get("oneOf", [body])
    }


def check_documented(response: Response) -> None:
    if response.status_code < 400:
        return
    response.read()
    method = response.request.method
    path = route_path(method, response.request.url.path)
    if path is None:
        return
    code = response.json()["code"]
    assert code in documented_codes(method, path, response.status_code), (
        f"{method} {path} sent a {response.status_code} {code}, "
        "which its responses= does not list"
    )


@pytest.fixture
def client() -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    client.event_hooks = {"response": [check_documented]}
    return client


def test_missing_todo(client: TestClient) -> None:
    response = client.get("/todos/99")
    assert response.json()["code"] == "todo_not_found"


def test_duplicate_title(client: TestClient) -> None:
    response = client.post("/todos", json={"title": "Buy milk"})
    assert response.json()["code"] == "duplicate_title"


def test_too_many_todos(client: TestClient) -> None:
    client.post("/todos", json={"title": "Water the plants"})
    response = client.post("/todos", json={"title": "Read a book"})
    assert response.json()["code"] == "too_many_todos"


def test_empty_title(client: TestClient) -> None:
    response = client.post("/todos", json={"title": ""})
    assert response.json()["code"] == "validation_error"


def test_unknown_path_and_method(client: TestClient) -> None:
    assert client.get("/nowhere").json()["code"] == "http_error"
    assert client.delete("/todos").json()["code"] == "http_error"


def test_every_route_documents_a_500() -> None:
    for path, operations in SCHEMA["paths"].items():
        for method, operation in operations.items():
            assert "500" in operation["responses"], f"{method.upper()} {path}"


def test_no_route_falls_back_to_fastapis_422() -> None:
    assert "HTTPValidationError" not in SCHEMA["components"]["schemas"]
