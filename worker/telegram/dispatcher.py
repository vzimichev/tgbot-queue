from aiogram import Dispatcher

from worker.telegram.routes import router

dp = Dispatcher()
dp.include_router(router)
