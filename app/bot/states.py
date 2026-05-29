from aiogram.fsm.state import State, StatesGroup

class AddSearchForm(StatesGroup):
    waiting_for_keyword = State()
    waiting_for_platforms = State()  
    waiting_for_min_price = State()
    waiting_for_max_price = State()