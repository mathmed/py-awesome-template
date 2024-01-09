
from http import HTTPStatus

from fastapi import APIRouter, Request, Response

from app.domain.services.helpers.errors import InvalidFieldError
from app.domain.services.helpers.errors.user_errors import EmailAlreadyExistsError
from app.domain.usecases.users.create import CreateUserParams, CreateUserResponse
from app.presentation.factories.usecases_factories import create_user_factory
from app.presentation.fastapi.middlewares.auth_middleware import auth_middleware

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.post("", status_code=HTTPStatus.CREATED, responses={
    # This FastAPI feature generates the OpenAPI schema automatically
    HTTPStatus.CREATED.value: {"description": "Success", "model": CreateUserResponse},
    HTTPStatus.BAD_REQUEST.value: {"description": "Validation error"},
})
async def create_user(request: Request, response: Response, body: CreateUserParams):
    try:
        return create_user_factory().execute(body)
    except InvalidFieldError as error:
        response.status_code = HTTPStatus.BAD_REQUEST
        return {"error": str(error)}
    except EmailAlreadyExistsError as error:
        response.status_code = HTTPStatus.CONFLICT
        return {"error": str(error)}
    except Exception:
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
        return response


@router.get("/some-authenticated-route", status_code=HTTPStatus.OK)
@auth_middleware
async def some_authenticated_route(request: Request, response: Response):
    return {"message": "Authenticated route"}
