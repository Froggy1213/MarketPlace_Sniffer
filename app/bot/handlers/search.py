import re
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.tasks import add_search_task, get_user_tasks, delete_search_task, count_user_tasks
from app.services.users import get_user_tier
from app.bot.states import AddSearchForm
from app.bot.keyboards import get_platforms_keyboard, get_price_keyboard, get_delete_task_keyboard
from app.bot.handlers.billing import send_pro_invoice

search_router = Router()

@search_router.message(Command("list"))
@search_router.message(F.text == "📋 My tasks")
async def cmd_list(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text or not message.from_user:
        return

    await state.clear() 

    tasks = await get_user_tasks(session, message.from_user.id)
    if not tasks:
        await message.answer("📭 Your task list is empty.")
        return
    
    await message.answer("📋 <b>Your Active Searches:</b>", parse_mode="HTML")
    for task in tasks:
        # Теперь из БД будет приходить нормальная строка, просто наводим красоту
        platforms_str = str(task.platforms).replace(",", ", ").upper()
        
        price_text = f"¥{task.min_price or 0} - ¥{task.max_price or '∞'}"
        text = (
            f"🎯 <b>{task.keyword}</b>\n"
            f"🛒 {platforms_str}\n"
            f"💰 {price_text}"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_delete_task_keyboard(task.id))

@search_router.callback_query(F.data.startswith("delete_task_"))
async def process_delete_task(callback: CallbackQuery, session: AsyncSession):
    if not callback.message or not callback.from_user:
        return
        
    task_id = int(callback.data.replace("delete_task_", ""))
    success = await delete_search_task(session, task_id, callback.from_user.id)
    
    if success:
        await callback.message.edit_text("🗑 <b>Task deleted.</b>", parse_mode="HTML")
    else:
        await callback.answer("Error deleting task or task not found.", show_alert=True)


@search_router.message(Command("add"))
@search_router.message(F.text == "➕ New search")
async def cmd_add(message: Message, state: FSMContext, session: AsyncSession):
    if not message.from_user:
        return

    tier = await get_user_tier(session, message.from_user.id)
    active_tasks = await count_user_tasks(session, message.from_user.id)
    
    limit = 2 if tier == "free" else 30
    if active_tasks >= limit:
        if tier == "free":
            await message.answer("⚠️ You have reached the limit of 2 tasks for the free tier.\nUpgrade to PRO to add more.")
            await send_pro_invoice(message)
        else:
            await message.answer(f"⚠️ You have reached the PRO limit of {limit} tasks.")
        return

    await state.set_state(AddSearchForm.waiting_for_keyword)
    await message.answer("📝 Enter the <b>keyword</b> you want to search for (e.g., 'MacBook Pro M2'):", parse_mode="HTML")


@search_router.message(AddSearchForm.waiting_for_keyword)
async def process_keyword(message: Message, state: FSMContext):
    if not message.text:
        return
    await state.update_data(keyword=message.text.strip())
    await state.set_state(AddSearchForm.waiting_for_platforms)
    await message.answer("🛒 Select the <b>marketplaces</b> to search on:", parse_mode="HTML", reply_markup=get_platforms_keyboard())


@search_router.callback_query(AddSearchForm.waiting_for_platforms)
async def process_platforms(callback: CallbackQuery, state: FSMContext):
    if not callback.message:
        return
        
    if callback.data == "platforms_done":
        data = await state.get_data()
        if not data.get('platforms'):
            await callback.answer("Please select at least one platform!", show_alert=True)
            return
        await state.set_state(AddSearchForm.waiting_for_min_price)
        await callback.message.edit_text("💰 Select or enter the <b>minimum price</b> (¥):", parse_mode="HTML", reply_markup=get_price_keyboard("min"))
        
    elif callback.data == "platforms_all":
        # Логика для кнопки "All platforms"
        all_platforms = ["mercari", "yahoo", "rakuma", "rakuten", "paypay"]
        await state.update_data(platforms=all_platforms)
        await callback.message.edit_reply_markup(reply_markup=get_platforms_keyboard(all_platforms))
        
    else:
        # Логика выбора конкретной платформы (тогл)
        platform = callback.data.replace("platform_", "")
        data = await state.get_data()
        
        current_platforms = data.get('platforms', [])
        if isinstance(current_platforms, str):
            current_platforms = [p.strip() for p in current_platforms.split(',')] if current_platforms else []
            
        if platform in current_platforms:
            current_platforms.remove(platform)
        else:
            current_platforms.append(platform)
            
        await state.update_data(platforms=current_platforms)
        await callback.message.edit_reply_markup(reply_markup=get_platforms_keyboard(current_platforms))


@search_router.callback_query(AddSearchForm.waiting_for_min_price)
async def process_min_price_callback(callback: CallbackQuery, state: FSMContext):
    if not callback.message:
        return
    price = int(callback.data.replace("price_min_", ""))
    await state.update_data(min_price=price if price > 0 else None)
    await state.set_state(AddSearchForm.waiting_for_max_price)
    await callback.message.edit_text("💰 Select or enter the <b>maximum price</b> (¥):", parse_mode="HTML", reply_markup=get_price_keyboard("max"))


@search_router.message(AddSearchForm.waiting_for_min_price)
async def process_min_price_msg(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("⚠️ Please enter numbers only. Try again:")
        return
    await state.update_data(min_price=int(message.text))
    await state.set_state(AddSearchForm.waiting_for_max_price)
    await message.answer("💰 Select or enter the <b>maximum price</b> (¥):", parse_mode="HTML", reply_markup=get_price_keyboard("max"))

@search_router.callback_query(AddSearchForm.waiting_for_max_price)
async def process_max_price_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    if not callback.message or not callback.from_user:
        return
    price = int(callback.data.replace("price_max_", ""))
    # Передаем callback.from_user.id (ID юзера), а не callback.message.from_user.id (ID бота)
    await finalize_task_creation(callback.message, callback.from_user.id, state, session, price)


@search_router.message(AddSearchForm.waiting_for_max_price)
async def process_max_price_msg(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text or not message.text.isdigit():
        await message.answer("⚠️ Please enter numbers only. Try again:")
        return
    await finalize_task_creation(message, message.from_user.id, state, session, int(message.text))


async def finalize_task_creation(message_to_reply: Message, user_id: int, state: FSMContext, session: AsyncSession, max_price: int):
    data = await state.get_data()
    
    platforms = data['platforms']
    if isinstance(platforms, str):
        platforms = [p.strip() for p in platforms.split(',')]
        
    success = await add_search_task(
        session=session,
        user_id=user_id,
        keyword=data['keyword'],
        platforms=platforms,
        min_price=data.get('min_price'),
        max_price=max_price if max_price > 0 else None
    )
    
    await state.clear()

    if success:
        platforms_display = ", ".join(platforms)
        await message_to_reply.answer(
            f"✅ <b>Task created successfully!</b>\n\n"
            f"🎯 <b>Keyword:</b> {data['keyword']}\n"
            f"🛒 <b>Markets:</b> {platforms_display.upper()}",
            parse_mode="HTML"
        )
    else:
        await message_to_reply.answer("⚠️ This task already exists or an error occurred.")