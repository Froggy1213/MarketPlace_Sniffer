"""Search task management handlers.

This module handles creating, listing, and deleting marketplace search tasks.
It manages the FSM (Finite State Machine) for multi-step task creation flow.
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.services.storage import (
    add_search_task, get_user_tasks, delete_search_task, 
    get_user_tier, count_user_tasks
)
from app.bot.states import AddSearchForm
from app.bot.keyboards import get_platforms_keyboard, get_price_keyboard, get_delete_task_keyboard
from app.bot.handlers.billing import send_pro_invoice

# Router for search task management message and callback handlers
search_router = Router()

# Decorator stacking: this function handles both /list command and menu button
@search_router.message(Command("list"))
@search_router.message(F.text == "📋 My tasks")
async def cmd_list(message: Message):
    """Display all active search tasks for the user.
    
    Retrieves and displays each task with keyword, price range, and marketplaces.
    Each task includes a delete button for quick removal.
    """
    # Validate message and user
    if not message.text or not message.from_user:
        return

    # Get user's active search tasks
    tasks = await get_user_tasks(message.from_user.id)
    if not tasks:
        await message.answer("📭 Your task list is empty.")
        return
    
    # Send header message
    await message.answer("<b>📋 Your active tasks:</b>", parse_mode="HTML")
    
    # Display each task with details and delete button
    for t in tasks:
        # Format price range (show infinity symbol if no max price)
        prices = f" (¥{t.min_price or 0} - ¥{t.max_price or '∞'})" if t.min_price or t.max_price else ""
        text = f"🔹 <b>{t.keyword}</b>{prices}\n🛒 Markets: {t.platforms}"
        await message.answer(text, parse_mode="HTML", reply_markup=get_delete_task_keyboard(t.id))

@search_router.callback_query(F.data.startswith("delete_task_"))
async def process_delete_task(callback: CallbackQuery):
    """Handle task deletion when user clicks delete button.
    
    Removes the task from database and marks it as deleted in the message.
    """
    # Validate callback data and message
    if not callback.data or not isinstance(callback.message, Message):
        return

    # Extract task ID from callback data
    task_id = int(callback.data.replace("delete_task_", ""))
    
    # Delete task from database
    success = await delete_search_task(task_id, callback.from_user.id)
    
    # Update message based on deletion result
    if success:
        # Strike through the task text and mark as deleted
        await callback.message.edit_text(
            f"<s>{callback.message.html_text}</s>\n\n🗑 <b>Deleted</b>",
            parse_mode="HTML",
            reply_markup=None
        )
    else:
        # Show error if task not found
        await callback.answer("❌ Error: task not found.", show_alert=True)
    
    # Acknowledge callback
    await callback.answer()

@search_router.message(Command("add"))
@search_router.message(F.text == "➕ New search")
async def cmd_add(message: Message, state: FSMContext):
    """Start the task creation flow.
    
    Checks user tier and task limits. If limit reached, offers PRO upgrade.
    Otherwise, begins multi-step task creation with platform selection.
    """
    # Validate user
    if not message.from_user:
        return
    
    # Get user subscription tier and active task count
    tier = await get_user_tier(message.from_user.id)
    active_tasks = await count_user_tasks(message.from_user.id)
    
    # Set task limit based on tier (2 for free, 30 for PRO)
    limit = 2 if tier == "free" else 30
    
    # Check if user reached task limit
    if active_tasks >= limit:
        # Notify user about limit and offer upgrade
        await message.answer(
            f"⚠️ <b>Task limit reached!</b>\n\n"
            f"Your tier: <b>{tier.upper()}</b> ({active_tasks}/{limit} tasks).\n\n"
            "Upgrade to PRO to add more searches and receive notifications without delays.",
            parse_mode="HTML"
        )
        # Send PRO upgrade invoice
        await send_pro_invoice(message)
        return

    # Show marketplace selection keyboard
    await message.answer("Select a marketplace to search:", reply_markup=get_platforms_keyboard())
    # Move FSM to platform selection state
    await state.set_state(AddSearchForm.waiting_for_platform)

@search_router.callback_query(AddSearchForm.waiting_for_platform, F.data.startswith("platform_"))
async def process_platform_selection(callback: CallbackQuery, state: FSMContext):
    """Handle marketplace platform selection.
    
    Stores selected platform in FSM data and prompts for search keyword.
    """
    # Validate callback data and message
    if not callback.data or not isinstance(callback.message, Message):
        return

    # Extract platform name and store in FSM
    selected_platform = callback.data.replace("platform_", "")
    await state.update_data(platforms=selected_platform)
    
    # Remove platform selection keyboard
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Prompt for keyword input
    await callback.message.answer("Enter a keyword (e.g. <i>ThinkPad X1 Carbon</i>):", parse_mode="HTML")
    # Move FSM to keyword input state
    await state.set_state(AddSearchForm.waiting_for_keyword)
    # Acknowledge callback
    await callback.answer()

@search_router.message(AddSearchForm.waiting_for_keyword)
async def process_keyword(message: Message, state: FSMContext):
    """Handle keyword input for search task.
    
    Stores keyword and prompts for minimum price.
    """
    # Validate message text
    if not message.text:
        return

    # Store keyword in FSM (strip whitespace)
    await state.update_data(keyword=message.text.strip())
    
    # Prompt for minimum price
    await message.answer(
        "Set the <b>MINIMUM</b> price in yen:\n<i>(Pick from the list or type a number)</i>",
        parse_mode="HTML",
        reply_markup=get_price_keyboard("min")
    )
    # Move FSM to minimum price state
    await state.set_state(AddSearchForm.waiting_for_min_price)

@search_router.callback_query(AddSearchForm.waiting_for_min_price, F.data.startswith("price_"))
async def process_min_price_callback(callback: CallbackQuery, state: FSMContext):
    """Handle minimum price button selection.
    
    Stores minimum price and prompts for maximum price.
    """
    # Validate callback data and message
    if not callback.data or not isinstance(callback.message, Message):
        return

    # Extract price from callback data
    price = int(callback.data.replace("price_", ""))
    # Store price (None if price is 0, meaning no minimum)
    await state.update_data(min_price=price if price > 0 else None)
    
    # Remove price keyboard
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Ask for maximum price
    await ask_max_price(callback.message, state)
    # Acknowledge callback
    await callback.answer()

@search_router.message(AddSearchForm.waiting_for_min_price)
async def process_min_price_text(message: Message, state: FSMContext):
    """Handle minimum price text input.
    
    Validates numeric input and prompts for maximum price.
    """
    # Validate that input contains only digits
    if not message.text or not message.text.isdigit():
        await message.answer("⚠️ Please enter numbers only. Try again:")
        return

    # Store minimum price
    price = int(message.text)
    await state.update_data(min_price=price if price > 0 else None)
    
    # Ask for maximum price
    await ask_max_price(message, state)

async def ask_max_price(message_or_callback: Message, state: FSMContext):
    """Prompt user to enter maximum price.
    
    Helper function used by both callback and text input handlers.
    """
    # Display maximum price prompt with keyboard
    await message_or_callback.answer(
        "Set the <b>MAXIMUM</b> price in yen:\n<i>(Pick from the list or type a number)</i>",
        parse_mode="HTML",
        reply_markup=get_price_keyboard("max")
    )
    # Move FSM to maximum price state
    await state.set_state(AddSearchForm.waiting_for_max_price)

@search_router.callback_query(AddSearchForm.waiting_for_max_price, F.data.startswith("price_"))
async def process_max_price_callback(callback: CallbackQuery, state: FSMContext):
    """Handle maximum price button selection.
    
    Finalizes task creation with all parameters.
    """
    # Validate callback data and message
    if not callback.data or not isinstance(callback.message, Message):
        return

    # Extract price from callback data
    price = int(callback.data.replace("price_", ""))
    
    # Remove price keyboard
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Create the task with all collected parameters
    await finalize_task_creation(callback.message, state, price)
    # Acknowledge callback
    await callback.answer()

@search_router.message(AddSearchForm.waiting_for_max_price)
async def process_max_price_text(message: Message, state: FSMContext):
    """Handle maximum price text input.
    
    Validates numeric input and finalizes task creation.
    """
    # Validate that input contains only digits
    if not message.text or not message.text.isdigit():
        await message.answer("⚠️ Please enter numbers only. Try again:")
        return
    
    # Create the task with all collected parameters
    await finalize_task_creation(message, state, int(message.text))

async def finalize_task_creation(message: Message, state: FSMContext, max_price: int):
    """Create the search task with all collected parameters.
    
    Saves task to database and sends confirmation to user.
    Handles duplicate task detection.
    """
    # Retrieve all task parameters from FSM
    data = await state.get_data()
    
    # Create task in database
    success = await add_search_task(
        user_id=message.chat.id,
        keyword=data['keyword'],
        platforms=data['platforms'],
        min_price=data.get('min_price'),
        max_price=max_price if max_price > 0 else None
    )
    
    # Clear FSM state after task creation
    await state.clear()

    # Send appropriate response based on task creation result
    if success:
        # Format platform names for display (comma-separated to space-separated)
        platforms_display = data['platforms'].replace(',', ', ')
        await message.answer(
            f"✅ <b>Task created successfully!</b>\n\n"
            f"🎯 <b>Keyword:</b> {data['keyword']}\n"
            f"🛒 <b>Markets:</b> {platforms_display.upper()}",
            parse_mode="HTML"
        )
    else:
        # Notify user if duplicate task already exists
        await message.answer("⚠️ This task already exists in your list.")