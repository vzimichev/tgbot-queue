from fastapi import FastAPI

from api.routes.webhook import webhook_router
from core.logger import setup_logging

setup_logging()
app = FastAPI()

app.include_router(webhook_router)
