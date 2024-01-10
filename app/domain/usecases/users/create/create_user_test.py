from unittest import TestCase
from unittest.mock import create_autospec

from faker import Faker
from pytest import fixture

from app.domain.contracts import DatabaseContract
from app.domain.entities.models import User
from app.domain.services.helpers.errors import EmailAlreadyExistsError, InvalidFieldError

from .create_user import CreateUser, CreateUserParams, CreateUserResponse


@fixture
def sut():
    return CreateUser(
        database=create_autospec(DatabaseContract)
    )


@fixture
def params(faker: Faker):
    return CreateUserParams(
        email=faker.email(),
        password=faker.bothify('#' * 6),
        name=faker.name()
    )


def test_should_raise_on_invalid_email(faker: Faker, sut: CreateUser, params: CreateUserParams):
    with TestCase().assertRaises(InvalidFieldError):
        # Given
        params.email = faker.word()
        # When
        sut.execute(params)


def test_should_raise_on_invalid_name(sut: CreateUser, params: CreateUserParams):
    with TestCase().assertRaises(InvalidFieldError):
        # Given
        params.name = ''
        # When
        sut.execute(params)


def test_should_raise_on_invalid_password(sut: CreateUser, params: CreateUserParams):
    with TestCase().assertRaises(InvalidFieldError):
        # Given
        params.password = ''
        # When
        sut.execute(params)


def test_should_raise_if_user_already_exists(sut: CreateUser, params: CreateUserParams, faker: Faker):
    with TestCase().assertRaises(EmailAlreadyExistsError):
        # Given
        sut._database.find_one.return_value = User(
            id=faker.word(),
            name=faker.email(),
            email=params.email,
            password=faker.word()
        )
        # When
        sut.execute(params)

    # Then
    sut._database.find_one.assert_called_once_with(
        model=User,
        by='email',
        value=params.email
    )


def test_should_return_user_on_success(sut: CreateUser, params: CreateUserParams, faker: Faker):
    # Given
    sut._database.find_one.return_value = None
    sut._database.insert.return_value = User(
        id=faker.word(),
        name=params.name,
        email=params.email,
        password=params.password
    )
    # When
    response = sut.execute(params)

    # Then
    sut._database.find_one.assert_called_once_with(
        model=User,
        by='email',
        value=params.email
    )
    sut._database.insert.assert_called_once()
    assert isinstance(response, CreateUserResponse)
    assert response.name == params.name
    assert response.email == params.email
    assert response.id == sut._database.insert.return_value.id
