from aiogram.fsm.state import State, StatesGroup

class DownloadState(StatesGroup):
    waiting_for_link = State()

class AdminState(StatesGroup):
    broadcast_text = State()
    broadcast_media = State()
    broadcast_buttons = State()
    broadcast_confirm = State()
    
    add_channel = State()

class ScheduleState(StatesGroup):
    """States for scheduling downloads."""
    waiting_for_time = State()  # Waiting for custom time input
