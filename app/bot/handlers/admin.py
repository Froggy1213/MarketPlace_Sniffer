from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin import get_system_stats
from app.core.config import settings

admin_router = Router()

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession):
    if not message.text or not message.from_user:
        return
    
    if message.from_user.id != settings.ADMIN_ID:
        return

    stats = await get_system_stats(session)
    
    text = (
        "👑 <b>Admin Dashboard</b>\n\n"
        f"📊 <b>Active tasks:</b> {stats['active_tasks']}\n"
        f"📦 <b>Items in database:</b> {stats['total_found_items']}\n\n"
        "<i>To manage users, use direct database connection.</i>"
    )
    await message.answer(text, parse_mode="HTML")