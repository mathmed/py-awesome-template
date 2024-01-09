from http import HTTPStatus

from fastapi import APIRouter, Request, Response

from app.domain.usecases.signin import SigninParams, SigninResponseData
from app.presentation.factories.usecases_factories import signin_factory

router = APIRouter(
    tags=["Auth"],
)


@router.post("/signin", responses={
    # This FastAPI feature generates the OpenAPI schema automatically
    HTTPStatus.OK.value: {"description": "Success", "model": SigninResponseData},
    HTTPStatus.UNAUTHORIZED.value: {"description": "Unauthorized"},
})
async def signin(request: Request, response: Response, body: SigninParams):
    result = signin_factory().execute(body)
    if not result.authorized:
        response.status_code = HTTPStatus.UNAUTHORIZED
        return response
    return result.data
