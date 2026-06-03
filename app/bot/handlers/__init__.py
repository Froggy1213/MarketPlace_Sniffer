from aiogram import Router

from .admin import admin_router
from .billing import billing_router
from .common import common_router
from .errors import error_router
from .search import search_router

main_router = Router()

main_router.include_router(common_router)
main_router.include_router(admin_router)
main_router.include_router(billing_router)
main_router.include_router(search_router)
main_router.include_router(error_router)
