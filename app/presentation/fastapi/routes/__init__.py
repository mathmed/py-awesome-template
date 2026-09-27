# Register all routers here to be automatically applied in app/presentation/fastapi/configs/configs.py
from .example_routes import router as example_router

routers = [example_router]
