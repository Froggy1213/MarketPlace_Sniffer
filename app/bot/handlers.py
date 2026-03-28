from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.services.storage import add_search_task, get_user_tasks, delete_search_task
from app.core.config import settings
from app.bot.states import AddSearchForm
from app.bot.keyboards import get_platforms_keyboard

router = Router()


def is_admin(user_id: int) -> bool:
    """Check if the user has admin privileges."""
    return user_id == settings.ADMIN_ID


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return

    # Clear state in case user restarted the bot during an active FSM flow
    await state.clear()

    await message.answer(
        "👋 <b>Welcome, Hunter!</b>\n\n"
        "Commands:\n"
        "➕ /add — Create a new search task\n"
        "📋 /list — View active tasks\n"
        "🗑 /del ID — Delete a task",
        parse_mode="HTML"
    )


# --- FSM FLOW: ADDING A NEW SEARCH TASK ---

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return

    # Step 1: Ask for platform and set state
    await message.answer(
        "Select the target marketplace:",
        reply_markup=get_platforms_keyboard()
    )
    await state.set_state(AddSearchForm.waiting_for_platform)


@router.callback_query(AddSearchForm.waiting_for_platform, F.data.startswith("platform_"))
async def process_platform_selection(callback: CallbackQuery, state: FSMContext):
    # Extract platforms from callback data (e.g., "platform_mercari,yahoo" -> "mercari,yahoo")
    selected_platform = callback.data.replace("platform_", "")

    # Store the choice in FSM memory
    await state.update_data(platforms=selected_platform)

    # Remove inline keyboard from the previous message
    await callback.message.edit_reply_markup(reply_markup=None)

    # Step 2: Ask for keyword
    await callback.message.answer("Enter the keyword (e.g., ThinkPad X1 Carbon):")
    await state.set_state(AddSearchForm.waiting_for_keyword)
    await callback.answer()


@router.message(AddSearchForm.waiting_for_keyword)
async def process_keyword(message: Message, state: FSMContext):
    await state.update_data(keyword=message.text.strip())

    # Step 3: Ask for min price
    await message.answer(
        "Enter the MINIMUM price in JPY (digits only).\n"
        "Or type '0' to skip."
    )
    await state.set_state(AddSearchForm.waiting_for_min_price)


@router.message(AddSearchForm.waiting_for_min_price)
async def process_min_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Please enter numbers only. Try again:")
        return

    min_price = int(message.text)
    await state.update_data(min_price=min_price if min_price > 0 else None)

    # Step 4: Ask for max price
    await message.answer(
        "Enter the MAXIMUM price in JPY (digits only).\n"
        "Or type '0' to skip."
    )
    await state.set_state(AddSearchForm.waiting_for_max_price)


@router.message(AddSearchForm.waiting_for_max_price)
async def process_max_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Please enter numbers only. Try again:")
        return

    max_price = int(message.text)

    # Retrieve all collected data from FSM memory
    data = await state.get_data()

    # Save the new task to PostgreSQL
    success = await add_search_task(
        user_id=message.from_user.id,
        keyword=data['keyword'],
        platforms=data['platforms'],
        min_price=data.get('min_price'),
        max_price=max_price if max_price > 0 else None
    )

    # Clear FSM state
    await state.clear()

    if success:
        await message.answer(f"✅ <b>Task created!</b>\nTarget: {data['keyword']}", parse_mode="HTML")
    else:
        await message.answer("⚠️ This search task already exists in your list.")


# --- OTHER COMMANDS ---

@router.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin(message.from_user.id): return

    # Fetch tasks specific to this user
    tasks = await get_user_tasks(message.from_user.id)
    if not tasks:
        await message.answer("📭 Your task list is empty.")
        return

    text = "<b>📋 Active Tasks:</b>\n\n"
    for t in tasks:
        prices = f" (¥{t.min_price or 0} - ¥{t.max_price or '∞'})" if t.min_price or t.max_price else ""
        text += f"🔹 <b>ID: {t.id}</b> | {t.keyword}{prices} [{t.platforms}]\n"

    text += "\nTo delete a task, use: <code>/del ID</code>"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("del"))
async def cmd_del(message: Message):
    if not is_admin(message.from_user.id): return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("⚠️ Format: <code>/del ID</code>", parse_mode="HTML")
        return

    task_id = int(parts[1])
    # Ensure the user can only delete their own tasks
    success = await delete_search_task(task_id, message.from_user.id)

    if success:
        await message.answer(f"🗑 Task <b>ID {task_id}</b> has been deleted.", parse_mode="HTML")
    else:
        await message.answer("❌ Task not found or access denied.")