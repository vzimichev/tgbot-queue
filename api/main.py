from fastapi import FastAPI

from api.admin_webhook import admin_webhook_router
from api.telegram_webhook import webhook_router
from shared.logger import setup_logging

setup_logging()
app = FastAPI()

app.include_router(webhook_router)
app.include_router(admin_webhook_router)
