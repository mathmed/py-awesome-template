from app.common.logger import configure_logging
from app.common.settings import get_settings
from app.presentation.fastapi.configs.configs import make_fastapi_app

settings = get_settings()
configure_logging(settings)
app = make_fastapi_app(settings)
