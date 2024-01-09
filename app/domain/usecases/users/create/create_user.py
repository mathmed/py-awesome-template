
from typing import Dict, Optional
from uuid import uuid4

from app.domain.contracts import DatabaseContract
from app.domain.contracts.usecase import InputData, Usecase
from app.domain.entities.models.user import User
from app.domain.services.helpers.errors import Error
from app.domain.services.helpers.hash import encrypt
from app.domain.services.helpers.validations import is_valid_email, is_valid_name, is_valid_password


class CreateUserParams(InputData):
    name: str
    email: str
    password: str


class CreateUserResponse(InputData):
    success: bool
    data: Optional[Dict] = None
    errorMessage: Optional[str] = None


class CreateUser(Usecase):

    _params: CreateUserParams

    def __init__(
        self,
        database: DatabaseContract
    ) -> None:
        self._database = database

    def execute(self, params: CreateUserParams) -> CreateUserResponse:

        try:
            self._params = params

            self._validate_params()
            self._verify_if_already_exists()
            # this is only an example, you can add more validations on a real project

            user = self._insert_user()

            return CreateUserResponse(
                data=self._mount_response_data(user),
                success=True
            )

        except Error as error:
            return CreateUserResponse(
                success=False,
                errorMessage=str(error)
            )

    def _mount_response_data(self, user: User) -> Dict:
        return {
            'id': user.id,
            'name': user.name,
            'email': user.email
        }

    def _validate_params(self):
        if not is_valid_email(self._params.email):
            raise Error('Invalid email format')
        if not is_valid_name(self._params.name):
            raise Error('Invalid name - must be at least 3 characters')
        if not is_valid_password(self._params.password):
            raise Error('Invalid password - must be at least 6 characters')

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
            raise Error('Email already exists')
