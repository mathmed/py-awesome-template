
from uuid import uuid4

from app.domain.contracts import DatabaseContract
from app.domain.contracts.usecase import InputData, Usecase
from app.domain.entities.models.user import User
from app.domain.services.helpers.errors import EmailAlreadyExistsError, InvalidFieldError
from app.domain.services.helpers.hash import encrypt
from app.domain.services.helpers.validations import is_valid_email, is_valid_name, is_valid_password


class CreateUserParams(InputData):
    name: str
    email: str
    password: str


class CreateUserResponse(InputData):
    id: str
    name: str
    email: str


class CreateUser(Usecase):

    _params: CreateUserParams

    def __init__(
        self,
        database: DatabaseContract
    ) -> None:
        self._database = database

    def execute(self, params: CreateUserParams) -> CreateUserResponse:
        """
            raises InvalidFieldError, EmailAlreadyExistsError, Exception
        """

        try:
            self._params = params

            self._validate_params()
            self._verify_if_already_exists()
            # this is only an example, you can add more validations on a real project

            user = self._insert_user()

            return CreateUserResponse(
                id=user.id,
                name=user.name,
                email=user.email
            )

        except Exception as error:
            raise error

    def _validate_params(self):
        if not is_valid_email(self._params.email):
            raise InvalidFieldError('email')
        if not is_valid_name(self._params.name):
            raise InvalidFieldError('name')
        if not is_valid_password(self._params.password):
            raise InvalidFieldError('password')

    def _insert_user(self) -> User:
        return self._database.insert(
            model=User(
                id=str(uuid4()),
                name=self._params.name,
                email=self._params.email,
                password=encrypt(self._params.password)
            )
        )

    def _verify_if_already_exists(self):
        if self._database.find_one(
            model=User,
            by='email',
            value=self._params.email
        ):
            raise EmailAlreadyExistsError
