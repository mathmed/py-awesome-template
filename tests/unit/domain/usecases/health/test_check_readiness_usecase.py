from unittest.mock import MagicMock, create_autospec

from faker import Faker
from pytest import raises

from app.domain.contracts.readiness_check_contract import ReadinessCheckContract
from app.domain.enums.readiness_status import ReadinessStatus
from app.domain.errors.domain_errors import ServiceUnavailableError
from app.domain.usecases.health.check_readiness_usecase import (
    CheckReadinessParams,
    CheckReadinessUsecase,
    DependencyStatus,
)


def make_check(name: str, ready: bool) -> MagicMock:
    check: MagicMock = create_autospec(ReadinessCheckContract, instance=True)
    check.name = name
    check.is_ready.return_value = ready
    return check


def test_should_be_ready_when_there_are_no_dependencies() -> None:
    response = CheckReadinessUsecase(checks=[]).execute(CheckReadinessParams())
    assert response.status == ReadinessStatus.READY
    assert response.dependencies == []


def test_should_report_every_dependency_when_all_are_ready(faker: Faker) -> None:
    first, second = make_check(faker.word(), True), make_check(faker.word() + "2", True)
    response = CheckReadinessUsecase(checks=[first, second]).execute(CheckReadinessParams())
    assert response.status == ReadinessStatus.READY
    assert response.dependencies == [
        DependencyStatus(name=first.name, status=ReadinessStatus.READY),
        DependencyStatus(name=second.name, status=ReadinessStatus.READY),
    ]
    first.is_ready.assert_called_once_with()
    second.is_ready.assert_called_once_with()


def test_should_raise_naming_only_the_failed_dependencies() -> None:
    sut = CheckReadinessUsecase(
        checks=[
            make_check("database", False),
            make_check("cache", True),
            make_check("broker", False),
        ]
    )
    with raises(ServiceUnavailableError) as error:
        sut.execute(CheckReadinessParams())
    assert error.value.message == "Dependencies not ready: database, broker"
