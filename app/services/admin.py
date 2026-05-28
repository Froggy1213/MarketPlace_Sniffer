from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import SearchTask, FoundItem

async def get_system_stats(session: AsyncSession) -> dict:
    active_tasks_query = select(func.count(SearchTask.id)).where(SearchTask.is_active == True)
    active_tasks = await session.scalar(active_tasks_query)

    found_items_query = select(func.count(FoundItem.id))
    total_items = await session.scalar(found_items_query)

    return {
        "active_tasks": active_tasks or 0,
        "total_found_items": total_items or 0
    }