from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ New search"), KeyboardButton(text="📋 My tasks")],
            [KeyboardButton(text="ℹ️ Help")]
        ],
        resize_keyboard=True
    )

def get_platforms_keyboard(selected: list[str] = None) -> InlineKeyboardMarkup:
    if selected is None:
        selected = []
        
    builder = InlineKeyboardBuilder()
    platforms = ["mercari", "yahoo", "rakuma", "rakuten", "paypay"]
    
    for p in platforms:
        # Ставим галочку, если платформа уже выбрана
        text = f"✅ {p.capitalize()}" if p in selected else p.capitalize()
        builder.button(text=text, callback_data=f"platform_{p}")
        
    builder.button(text="🌐 All platforms", callback_data="platforms_all")
    builder.button(text="✅ Done", callback_data="platforms_done")
    
    builder.adjust(2, 2, 1, 2)
    return builder.as_markup()

def get_price_keyboard(price_type: str) -> InlineKeyboardMarkup:
    """price_type должен быть 'min' или 'max'"""
    builder = InlineKeyboardBuilder()
    prices = [0, 1000, 5000, 10000, 50000] if price_type == "min" else [0, 5000, 10000, 50000, 100000]
    
    for price in prices:
        text = f"¥{price}" if price > 0 else "Skip / Any"
        builder.button(text=text, callback_data=f"price_{price_type}_{price}")
        
    builder.adjust(2)
    return builder.as_markup()
    
def get_delete_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Delete", callback_data=f"delete_task_{task_id}")
    return builder.as_markup()