from aiogram.fsm.state import State, StatesGroup

class AddSearchForm(StatesGroup):
    """
    FSM states for the sequential process of adding a new search task.
    """
    waiting_for_platform = State()
    waiting_for_keyword = State()
    waiting_for_min_price = State()
    waiting_for_max_price = State()