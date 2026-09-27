from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.presentation.fastapi.routes as routes
from app.common.settings import Settings
from app.presentation.fastapi.handlers.domain_error_handler import register_error_handlers
from app.presentation.fastapi.middlewares.request_logging_middleware import (
    request_logging_middleware,
)


def apply_routes_config(app: FastAPI) -> None:
    """
    This function will apply all routers registered in app/presentation/fastapi/routes
    """
    for router in routes.routers:
        app.include_router(router)


def make_fastapi_app(settings: Settings) -> FastAPI:
    """
    This function will create a FastAPI instance and apply all routes defined in app/presentation/fastapi/routes
    """
    app = FastAPI(
        title=settings.app_name,
        description="A template for Python projects",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_logging_middleware)

    register_error_handlers(app)
    apply_routes_config(app)
    return app
