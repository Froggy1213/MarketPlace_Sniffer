"""Admin command handlers for MarketPlace Sniffer bot.

This module contains handlers for admin-only commands that display
system statistics and dashboard information.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.services.admin import get_system_stats
from app.core.config import settings

# Router for admin-specific message handlers
admin_router = Router()


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Handle /admin command to display system dashboard.
    
    Only accessible to the admin user specified in settings.ADMIN_ID.
    Displays statistics about active search tasks and items in database.
    """
    # Validate message and user
    if not message.text or not message.from_user:
        return
    
    # Check if user is authorized admin
    if message.from_user.id != settings.ADMIN_ID:
        return

    # Retrieve system statistics
    stats = await get_system_stats()
    
    # Format dashboard message with statistics
    text = (
        "👑 <b>Admin Dashboard</b>\n\n"
        f"📊 <b>Active tasks:</b> {stats['active_tasks']}\n"
        f"📦 <b>Items in database:</b> {stats['total_found_items']}\n\n"
        "<i>To manage users, use direct database connection.</i>"
    )
    
    # Send formatted message to admin
    await message.answer(text, parse_mode="HTML")