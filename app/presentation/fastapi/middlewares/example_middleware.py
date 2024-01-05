from typing import Any

from fastapi import Request


async def example_middleware(request: Request, call_next: Any) -> Any:
    """
        This is an example of a middleware that can be used to log all request
    """
    print(request)
    return await call_next(request)
