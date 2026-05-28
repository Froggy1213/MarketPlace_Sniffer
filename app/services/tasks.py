import logging
from typing import List, Optional
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import worker_session_maker as async_session_maker
from app.db.models import SearchTask

logger = logging.getLogger(__name__)

async def count_user_tasks(session: AsyncSession, telegram_id: int) -> int:
    query = select(func.count(SearchTask.id)).where(
        SearchTask.user_id == telegram_id, 
        SearchTask.is_active == True
    )
    return await session.scalar(query) or 0

async def add_search_task(session: AsyncSession, user_id: int, keyword: str, platforms: list[str], min_price: Optional[int] = None, max_price: Optional[int] = None) -> bool:
    query = select(SearchTask).where(SearchTask.user_id == user_id, SearchTask.keyword == keyword, SearchTask.platforms == platforms)
    result = await session.execute(query)
    if result.scalar_one_or_none():
        return False

    try:
        new_task = SearchTask(user_id=user_id, keyword=keyword, platforms=platforms, min_price=min_price, max_price=max_price)
        session.add(new_task)
        await session.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding task: {e}")
        await session.rollback()
        return False

async def get_user_tasks(session: AsyncSession, user_id: int) -> List[SearchTask]:
    query = select(SearchTask).where(SearchTask.is_active == True, SearchTask.user_id == user_id)
    result = await session.execute(query)
    return list(result.scalars().all())

async def delete_search_task(session: AsyncSession, task_id: int, user_id: int) -> bool:
    try:
        stmt = delete(SearchTask).where(SearchTask.id == task_id, SearchTask.user_id == user_id)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount > 0 
    except Exception as e:
        logger.error(f"Error deleting task: {e}")
        await session.rollback()
        return False

# === ВЫЗЫВАЕТСЯ ТОЛЬКО CELERY (БЕЗ MIDDLEWARE) ===
async def get_all_active_tasks() -> List[SearchTask]:
    async with async_session_maker() as session:
        result = await session.execute(select(SearchTask).where(SearchTask.is_active == True))
        return list(result.scalars().all())