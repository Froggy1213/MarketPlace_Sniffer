from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

# A dictionary mapping internal platform keys to their display names.
# This makes it incredibly easy to add or remove platforms in the future.
AVAILABLE_PLATFORMS = {
    "mercari": "🛍 Mercari",
    "yahoo": "🔨 Yahoo Auctions",
    "rakuma": "🧸 Rakuma",
    "rakuten": "🛒 Rakuten",
    "paypay": "📱 Yahoo Flea Market"
}


def get_platforms_keyboard() -> InlineKeyboardMarkup:
    """
    Generates an inline keyboard for marketplace selection dynamically.
    Utilizes InlineKeyboardBuilder for better layout management.
    """
    builder = InlineKeyboardBuilder()

    # Iterate through the dictionary and create a button for each platform
    for platform_key, platform_name in AVAILABLE_PLATFORMS.items():
        builder.button(
            text=platform_name,
            callback_data=f"platform_{platform_key}"
        )

    # Create a string containing all keys separated by commas (e.g., "mercari,yahoo,rakuma...")
    all_platforms_str = ",".join(AVAILABLE_PLATFORMS.keys())

    # Add a global button to search across all available platforms
    builder.button(
        text="✨ All Platforms",
        callback_data=f"platform_{all_platforms_str}"
    )

    # Adjust the layout automatically:
    # 2 buttons on the first row, 2 on the second, 1 on the third, 1 for "All Platforms"
    builder.adjust(2, 2, 1, 1)

    return builder.as_markup()