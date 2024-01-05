

from faker import Faker
from pytest import fixture

from .hello_world import HelloWorld, HelloWorldParams


@fixture
def sut() -> HelloWorld:
    return HelloWorld()


@fixture
def params(faker: Faker) -> HelloWorldParams:
    return HelloWorldParams(
        name=faker.word()
    )


def test_should_return_hello_world(sut: HelloWorld, params: HelloWorldParams) -> None:
    response = sut.execute(params)
    assert response.message == f"Hello {params.name}!"
