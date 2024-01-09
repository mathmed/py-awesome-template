from time import time
from typing import Optional

from app.domain.contracts import DatabaseContract, JWTContract
from app.domain.contracts.usecase import InputData, Usecase
from app.domain.entities.models import User
from app.domain.services.helpers.constants.auth import JWT_SECRET, JWT_TOKEN_ALIVE_TIME
from app.domain.services.helpers.errors import Error


class SigninParams(InputData):
    email: str
    password: str


class SigninResponseData(InputData):
    accessToken: str
    expiresIn: int


class SigninResponse(InputData):
    authorized: bool = False
    data: Optional[SigninResponseData] = None


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

        try:
            self._params = params
            user = self._get_user()
            self._verify_password(user)
            return SigninResponse(
                authorized=True,
                data=self._mount_access_token(user)
            )
        except Error:
            return SigninResponse(
                authorized=False,
            )

    def _verify_password(self, user: User):
        if not user.verify_password(self._params.password):
            raise Error('Invalid password')

    def _get_user(self) -> User:
        user = self._database.find_one(User, 'email', self._params.email)
        if not user:
            raise Error('User not found')
        return user

    def _mount_access_token(self, user: User) -> SigninResponseData:
        now = int(time())
        payload = {
            'iss': 'Example APP',
            'iat': now,
            'exp': now + JWT_TOKEN_ALIVE_TIME,
            'email': user.email
        }
        return SigninResponseData(
            accessToken=self._jwt.encode(
                payload=payload,
                secret=JWT_SECRET
            ),
            expiresIn=JWT_TOKEN_ALIVE_TIME
        )
