# Register all routers here to be automatically applied in app/presentation/fastapi/configs/configs.py
from .example_routes import router as example_router
from .health_routes import router as health_router
from .ready_routes import router as ready_router

routers = [health_router, ready_router, example_router]
