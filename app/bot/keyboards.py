from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

AVAILABLE_PLATFORMS = {
    "mercari": "🛍 Mercari",
    "yahoo": "🔨 Yahoo Auctions",
    "rakuma": "🧸 Rakuma",
    "rakuten": "🛒 Rakuten",
    "paypay": "📱 PayPay Flea Market"
}


def get_main_menu() -> ReplyKeyboardMarkup:
    """Bottom persistent menu (Reply Keyboard)"""
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ New search")
    builder.button(text="📋 My tasks")
    builder.button(text="ℹ️ Help")

    # 2 buttons in the top row, 1 in the bottom
    builder.adjust(2, 1)
    # resize_keyboard=True keeps buttons compact (not half the screen)
    return builder.as_markup(resize_keyboard=True)


def get_platforms_keyboard() -> InlineKeyboardMarkup:
    """Inline platform selection menu"""
    builder = InlineKeyboardBuilder()
    for platform_key, platform_name in AVAILABLE_PLATFORMS.items():
        builder.button(text=platform_name, callback_data=f"platform_{platform_key}")
    builder.button(text="✨ All platforms", callback_data=f"platform_{','.join(AVAILABLE_PLATFORMS.keys())}")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def get_price_keyboard(price_type: str) -> InlineKeyboardMarkup:
    """Price presets for quick input without typing"""
    builder = InlineKeyboardBuilder()

    if price_type == "min":
        builder.button(text="0 ¥ (Any price)", callback_data="price_0")
        builder.button(text="From 1,000 ¥", callback_data="price_1000")
        builder.button(text="From 5,000 ¥", callback_data="price_5000")
        builder.button(text="From 10,000 ¥", callback_data="price_10000")
    else:
        builder.button(text="♾ No limit", callback_data="price_0")
        builder.button(text="Up to 5,000 ¥", callback_data="price_5000")
        builder.button(text="Up to 10,000 ¥", callback_data="price_10000")
        builder.button(text="Up to 50,000 ¥", callback_data="price_50000")

    builder.adjust(1)  # All buttons stacked vertically for easy thumb tapping
    return builder.as_markup()


def get_delete_task_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Inline button for deleting a specific task"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Delete",
        callback_data=f"delete_task_{task_id}"
    )
    return builder.as_markup()