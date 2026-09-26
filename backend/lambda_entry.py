"""FastAPI adapter for a regional Lambda Function URL."""
from mangum import Mangum
from .server import app

handler = Mangum(app, lifespan='off')
