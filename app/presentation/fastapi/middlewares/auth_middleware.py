from asyncio import get_event_loop, iscoroutinefunction
from functools import partial, wraps
from http import HTTPStatus
from typing import Dict, Optional

from fastapi import Request

from app.domain.services.helpers.constants.auth import JWT_SECRET
from app.domain.services.helpers.errors import UnauthorizedError
from app.infra.jwt.jwt import JWT


def auth_middleware(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):

        response: object = kwargs.get('response', None)
        request: Request = kwargs.get('request', None)

        try:
            headers: Dict = request.headers  # type: ignore

            auth_header: Optional[str] = headers.get('Authorization', None)

            if not auth_header:
                raise UnauthorizedError

            auth_type, credentials = auth_header.split(' ')

            if auth_type.lower() != 'bearer':
                raise UnauthorizedError

            decoded_bearer = JWT().decode(
                secret=JWT_SECRET,
                text=credentials,
            )
            if not decoded_bearer:
                raise UnauthorizedError

        except Exception:
            response.status_code = HTTPStatus.UNAUTHORIZED  # type: ignore
            return response

        if iscoroutinefunction(func):
            return await func(*args, **kwargs)

        loop = get_event_loop()
        partial_route = partial(func, *args, **kwargs)
        return await loop.run_in_executor(None, partial_route)

    return wrapper
