from aiogram import Dispatcher

from worker.processors.faceswap.tgbot_routes import face_swap_router

dp = Dispatcher()

dp.include_router(face_swap_router)
