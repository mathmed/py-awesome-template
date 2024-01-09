

from app.domain.usecases.signin import Signin
from app.domain.usecases.users.create import CreateUser
from app.infra.database.mongodb.mongodb import MongoDB
from app.infra.jwt.jwt import JWT


def signin_factory() -> Signin:
    return Signin(
        database=MongoDB(),
        jwt=JWT()
    )


def create_user_factory() -> CreateUser:
    return CreateUser(
        database=MongoDB()
    )
