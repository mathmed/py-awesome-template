from unittest import TestCase
from unittest.mock import MagicMock, create_autospec, patch

from faker import Faker
from pytest import fixture

from app.domain.contracts import DatabaseContract, JWTContract
from app.domain.entities.models import User
from app.domain.services.helpers.errors.user_errors import InvalidPasswordError, UserNotFoundError

from .signin import Signin, SigninParams, SigninResponse


@fixture
def sut():
    return Signin(
        database=create_autospec(DatabaseContract),
        jwt=create_autospec(JWTContract)
    )


@fixture
def params(faker: Faker):
    return SigninParams(
        email=faker.email(),
        password=faker.word()
    )


def test_should_raise_if_user_not_found(sut: Signin, params: SigninParams):
    with TestCase().assertRaises(UserNotFoundError):
        # Given
        sut._database.find_one.return_value = None

        # When
        sut.execute(params)

    # Then
    sut._database.find_one.assert_called_once_with(
        model=User,
        by='email',
        value=params.email
    )


def test_should_raise_if_password_does_not_match(sut: Signin, params: SigninParams, faker: Faker):
    with TestCase().assertRaises(InvalidPasswordError):
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


@patch('app.domain.entities.models.user.compare', return_value=True)
def test_should_return_a_token_on_success(_: MagicMock, sut: Signin, params: SigninParams, faker: Faker):

    # Given
    user = User(
        id=faker.word(),
        name=faker.email(),
        email=params.email,
        password=params.password
    )
    sut._database.find_one.return_value = user
    sut._jwt.encode.return_value = faker.word()

    # When
    result = sut.execute(params)

    # Then
    assert isinstance(result, SigninResponse)
    assert result.accessToken == sut._jwt.encode.return_value
