"""Common handlers for general bot commands and menu interactions.

This module contains handlers for start command, help information,
and general user interactions.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from app.bot.keyboards import get_main_menu

# Router for common user interaction handlers
common_router = Router()


@common_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command to initialize conversation.
    
    Clears any previous FSM state and displays welcome message with main menu.
    """
    # Validate message
    if not message.text:
        return

    # Clear any existing FSM state from previous conversations
    await state.clear()
    
    # Send welcome message with main menu keyboard
    await message.answer(
        "👋 <b>Welcome to MarketPlace Sniffer!</b>\n\n"
        "I will continuously search for new items across Japan's top marketplaces.\n"
        "Use the menu below to get started:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )


@common_router.message(F.text == "ℹ️ Help")
async def handle_help_button(message: Message):
    """Handle help button press to display available commands.
    
    Shows user all available commands and their descriptions.
    """
    # Validate message
    if not message.text:
        return

    # Send help text with available commands
    await message.answer(
        "<b>Available commands:</b>\n"
        "<code>/add</code> — Create a new search task\n"
        "<code>/list</code> — Display active search tasks\n"
        "<code>/del ID</code> — Delete a task by its ID",
        parse_mode="HTML"
    )