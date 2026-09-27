from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import fixture, mark

from app.domain.common.errors.domain_errors import (
    ConflictError,
    DomainError,
    NotFoundError,
)
from app.presentation.fastapi.handlers.domain_error_handler import register_error_handlers


@fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise/{kind}")
    async def raise_error(kind: str) -> None:
        errors = {"not-found": NotFoundError, "conflict": ConflictError}
        raise errors.get(kind, DomainError)("some message")

    return TestClient(app)


@mark.parametrize(
    ("kind", "status_code"),
    [("not-found", 404), ("conflict", 409), ("generic", 400)],
)
def test_should_map_domain_errors_to_http_status(
    client: TestClient, kind: str, status_code: int
) -> None:
    response = client.get(f"/raise/{kind}")
    assert response.status_code == status_code
    assert response.json() == {"detail": "some message"}
