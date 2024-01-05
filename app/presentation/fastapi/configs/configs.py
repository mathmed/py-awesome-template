from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.presentation.fastapi.routes as routes


def apply_routes_config(app: FastAPI):
    """
        This function will apply automatically all routes defined in app/presentation/fastapi/routes
    """
    route_definitions = [
        getattr(routes, variable) for variable in dir(routes) if not variable.startswith('__')
    ]
    for router in route_definitions:
        try:
            app.include_router(router.router)
        except Exception:
            pass


def make_fastapi_app():
    """
        This function will create a FastAPI instance and apply all routes defined in app/presentation/fastapi/routes
    """
    app = FastAPI(
        title='Awesome Python Template',
        description='A template for Python projects',
    )
    app.add_middleware(
        CORSMiddleware,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    # To add general middlewares, uncomment the following lines
    # app.middleware('http')(some_middleware)

    apply_routes_config(app)
    return app
