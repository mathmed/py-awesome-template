from unittest.mock import MagicMock, create_autospec

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

import app.presentation.fastapi.routes.ready_routes as ready_routes
from app.domain.contracts.readiness_check_contract import ReadinessCheckContract
from app.domain.usecases.health.check_readiness_usecase import CheckReadinessUsecase
from app.main.main import app


def make_check(name: str, ready: bool) -> MagicMock:
    check: MagicMock = create_autospec(ReadinessCheckContract, instance=True)
    check.name = name
    check.is_ready.return_value = ready
    return check


def test_should_return_ready_without_dependencies() -> None:
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "dependencies": []}


def test_should_return_ready_when_dependencies_are_ready(monkeypatch: MonkeyPatch) -> None:
    usecase = CheckReadinessUsecase(checks=[make_check("database", True)])
    monkeypatch.setattr(ready_routes, "check_readiness_factory", lambda: usecase)
    response = TestClient(app).get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": [{"name": "database", "status": "ready"}],
    }


def test_should_return_503_when_a_dependency_is_not_ready(monkeypatch: MonkeyPatch) -> None:
    usecase = CheckReadinessUsecase(checks=[make_check("database", False)])
    monkeypatch.setattr(ready_routes, "check_readiness_factory", lambda: usecase)
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Dependencies not ready: database"}
