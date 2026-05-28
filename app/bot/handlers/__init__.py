"""Package for handling Telegram bot message routes and callbacks.

This module aggregates all handler routers (admin, billing, search, common)
and combines them into a single main router for the bot application.
"""
from aiogram import Router

from .admin import admin_router
from .billing import billing_router
from .search import search_router
from .common import common_router

# Create the main router for all handlers
main_router = Router()

# Router order is important: specific routers (admin, billing) must be registered
# before general ones (search, common) to ensure proper message routing priority
main_router.include_routers(
    admin_router,
    billing_router,
    search_router,
    common_router
)