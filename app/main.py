from fastapi import FastAPI

from app.api.webhook import router as webhook_router
from app.core.logger import setup_logging

setup_logging()
app = FastAPI()

app.include_router(webhook_router)
