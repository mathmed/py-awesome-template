# Register all routers here to be automatically applied in app/presentation/fastapi/configs/configs.py
from .example_routes import router as example_router
from .health_routes import router as health_router

routers = [health_router, example_router]
