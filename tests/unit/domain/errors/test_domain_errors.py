import pytest

from app.domain.errors.domain_errors import DomainError


@pytest.fixture
def sut() -> DomainError:
    return DomainError("something went wrong")


def test_should_expose_message_as_attribute_and_string(sut: DomainError) -> None:
    assert sut.message == "something went wrong"
    assert str(sut) == "something went wrong"
