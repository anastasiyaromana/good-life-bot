from aiogram.fsm.state import StatesGroup, State

class Form(StatesGroup):
    wait_time = State()
    q1 = State()
    q2 = State()
    q3 = State()
    q4 = State()
