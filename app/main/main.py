from dotenv import load_dotenv

# Load all environment variables from .env file before app starts
load_dotenv()

from app.presentation.fastapi.configs.configs import make_fastapi_app

app = make_fastapi_app()
