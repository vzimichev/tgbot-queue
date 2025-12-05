from aiogram import Dispatcher

from worker.telegram.routes import common_router

dp = Dispatcher()
dp.include_router(common_router)
