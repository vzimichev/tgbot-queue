from aiogram.fsm.state import State, StatesGroup


class UploadMediaState(StatesGroup):
    waiting_photo = State()
    waiting_video = State()
    ready_to_generate = State()
