"""FastAPI adapter for a regional Lambda Function URL."""
from mangum import Mangum
from .runtime_config import load_runtime_config

load_runtime_config()

from .server import app

handler = Mangum(app, lifespan='off')
