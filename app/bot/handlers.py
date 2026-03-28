from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.services.storage import add_search_task, get_user_tasks, delete_search_task
from app.core.config import settings
from app.bot.states import AddSearchForm
from app.bot.keyboards import get_platforms_keyboard, get_main_menu, get_price_keyboard, get_delete_task_keyboard

router = Router()


# --- START & MAIN MENU ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    # Clear state in case the bot was restarted mid-input
    await state.clear()

    await message.answer(
        "👋 <b>Welcome to MarketPlace Sniffer!</b>\n\n"
        "I will continuously search for new items across Japan's top marketplaces.\n"
        "Use the menu below to get started:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )


# Handle bottom menu button presses
@router.message(F.text == "➕ New search")
async def handle_new_search_button(message: Message, state: FSMContext):
    await cmd_add(message, state)


@router.message(F.text == "📋 My tasks")
async def handle_my_tasks_button(message: Message):
    await cmd_list(message)


@router.message(F.text == "ℹ️ Help")
async def handle_help_button(message: Message):
    await message.answer(
        "<b>Available commands:</b>\n"
        "<code>/add</code> — Create a new task\n"
        "<code>/list</code> — List active tasks\n"
        "<code>/del ID</code> — Delete a task by its ID",
        parse_mode="HTML"
    )


# --- FSM FLOW: ADDING A NEW SEARCH TASK ---

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    # Step 1: Platform selection
    await message.answer(
        "Select a marketplace to search:",
        reply_markup=get_platforms_keyboard()
    )
    await state.set_state(AddSearchForm.waiting_for_platform)


@router.callback_query(AddSearchForm.waiting_for_platform, F.data.startswith("platform_"))
async def process_platform_selection(callback: CallbackQuery, state: FSMContext):
    selected_platform = callback.data.replace("platform_", "")
    await state.update_data(platforms=selected_platform)

    # Remove the inline keyboard after selection
    await callback.message.edit_reply_markup(reply_markup=None)

    # Step 2: Keyword input
    await callback.message.answer("Enter a keyword (e.g. <i>ThinkPad X1 Carbon</i>):", parse_mode="HTML")
    await state.set_state(AddSearchForm.waiting_for_keyword)
    await callback.answer()


@router.message(AddSearchForm.waiting_for_keyword)
async def process_keyword(message: Message, state: FSMContext):
    await state.update_data(keyword=message.text.strip())

    # Step 3: Minimum price with presets
    await message.answer(
        "Set the <b>MINIMUM</b> price in yen:\n"
        "<i>(Pick from the list or type a number)</i>",
        parse_mode="HTML",
        reply_markup=get_price_keyboard("min")
    )
    await state.set_state(AddSearchForm.waiting_for_min_price)


# Handle minimum price (button press)
@router.callback_query(AddSearchForm.waiting_for_min_price, F.data.startswith("price_"))
async def process_min_price_callback(callback: CallbackQuery, state: FSMContext):
    price = int(callback.data.replace("price_", ""))
    await state.update_data(min_price=price if price > 0 else None)

    await callback.message.edit_reply_markup(reply_markup=None)
    await ask_max_price(callback.message, state)
    await callback.answer()


# Handle minimum price (manual text input)
@router.message(AddSearchForm.waiting_for_min_price)
async def process_min_price_text(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Please enter numbers only. Try again:")
        return

    price = int(message.text)
    await state.update_data(min_price=price if price > 0 else None)
    await ask_max_price(message, state)


async def ask_max_price(message_or_callback: Message, state: FSMContext):
    """Helper to transition to the maximum price step"""
    await message_or_callback.answer(
        "Set the <b>MAXIMUM</b> price in yen:\n"
        "<i>(Pick from the list or type a number)</i>",
        parse_mode="HTML",
        reply_markup=get_price_keyboard("max")
    )
    await state.set_state(AddSearchForm.waiting_for_max_price)


# Handle maximum price (button press)
@router.callback_query(AddSearchForm.waiting_for_max_price, F.data.startswith("price_"))
async def process_max_price_callback(callback: CallbackQuery, state: FSMContext):
    price = int(callback.data.replace("price_", ""))
    await callback.message.edit_reply_markup(reply_markup=None)
    await finalize_task_creation(callback.message, state, price)
    await callback.answer()


# Handle maximum price (manual text input)
@router.message(AddSearchForm.waiting_for_max_price)
async def process_max_price_text(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Please enter numbers only. Try again:")
        return
    price = int(message.text)
    await finalize_task_creation(message, state, price)


async def finalize_task_creation(message: Message, state: FSMContext, max_price: int):
    """Save the task to the database"""
    data = await state.get_data()

    success = await add_search_task(
        user_id=message.chat.id,
        keyword=data['keyword'],
        platforms=data['platforms'],
        min_price=data.get('min_price'),
        max_price=max_price if max_price > 0 else None
    )

    await state.clear()

    if success:
        platforms_display = data['platforms'].replace(',', ', ')
        await message.answer(
            f"✅ <b>Task created successfully!</b>\n\n"
            f"🎯 <b>Keyword:</b> {data['keyword']}\n"
            f"🛒 <b>Markets:</b> {platforms_display.upper()}",
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ This task already exists in your list.")


# --- OTHER COMMANDS ---

@router.message(Command("list"))
async def cmd_list(message: Message):
    tasks = await get_user_tasks(message.from_user.id)
    if not tasks:
        await message.answer("📭 Your task list is empty.")
        return
    await message.answer("<b>📋 Your active tasks:</b>", parse_mode="HTML")
    # Send each task as a separate message with a delete button
    for t in tasks:
        prices = f" (¥{t.min_price or 0} - ¥{t.max_price or '∞'})" if t.min_price or t.max_price else ""
        text = f"🔹 <b>{t.keyword}</b>{prices}\n🛒 Markets: {t.platforms}"
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_delete_task_keyboard(t.id)
        )


@router.callback_query(F.data.startswith("delete_task_"))
async def process_delete_task(callback: CallbackQuery):
    task_id = int(callback.data.replace("delete_task_", ""))
    success = await delete_search_task(task_id, callback.from_user.id)
    if success:
        # On success, strike through the message text and remove the button
        await callback.message.edit_text(
            f"<s>{callback.message.html_text}</s>\n\n🗑 <b>Deleted</b>",
            parse_mode="HTML",
            reply_markup=None
        )
    else:
        await callback.answer("❌ Error: task not found.", show_alert=True)
    await callback.answer()