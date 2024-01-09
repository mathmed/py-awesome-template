from http import HTTPStatus

from fastapi import APIRouter, Request, Response

from app.domain.services.helpers.errors import InvalidPasswordError, UserNotFoundError
from app.domain.usecases.signin import SigninParams, SigninResponse
from app.presentation.factories.usecases_factories import signin_factory

router = APIRouter(
    tags=["Auth"],
)


@router.post("/signin", responses={
    # This FastAPI feature generates the OpenAPI schema automatically
    HTTPStatus.OK.value: {"description": "Success", "model": SigninResponse},
    HTTPStatus.UNAUTHORIZED.value: {"description": "Unauthorized"},
})
async def signin(request: Request, response: Response, body: SigninParams):
    try:
        return signin_factory().execute(body)
    except (InvalidPasswordError, UserNotFoundError):
        response.status_code = HTTPStatus.UNAUTHORIZED
    except Exception:
        response.status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    return response
