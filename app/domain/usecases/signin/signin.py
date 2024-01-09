from time import time

from app.domain.contracts import DatabaseContract, JWTContract
from app.domain.contracts.usecase import InputData, Usecase
from app.domain.entities.models import User
from app.domain.services.helpers.constants.auth import JWT_SECRET, JWT_TOKEN_ALIVE_TIME
from app.domain.services.helpers.errors import InvalidPasswordError, UserNotFoundError


class SigninParams(InputData):
    email: str
    password: str


class SigninResponse(InputData):
    accessToken: str
    expiresIn: int


class Signin(Usecase):

    _params: SigninParams

    def __init__(
        self,
        database: DatabaseContract,
        jwt: JWTContract
    ) -> None:
        self._database = database
        self._jwt = jwt

    def execute(self, params: SigninParams) -> SigninResponse:
        """
            raises InvalidPasswordError, UserNotFoundError, Exception
        """

        try:
            self._params = params
            user = self._get_user()
            self._verify_password(user)
            return self._mount_response(user)
        except Exception as error:
            raise error

    def _verify_password(self, user: User):
        if not user.verify_password(self._params.password):
            raise InvalidPasswordError

    def _get_user(self) -> User:
        user = self._database.find_one(User, 'email', self._params.email)
        if not user:
            raise UserNotFoundError
        return user

    def _mount_response(self, user: User) -> SigninResponse:
        now = int(time())
        payload = {
            'iss': 'Example APP',
            'iat': now,
            'exp': now + JWT_TOKEN_ALIVE_TIME,
            'email': user.email
        }
        return SigninResponse(
            accessToken=self._jwt.encode(
                payload=payload,
                secret=JWT_SECRET
            ),
            expiresIn=JWT_TOKEN_ALIVE_TIME
        )
