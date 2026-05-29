import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func 
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User, SearchTask

logger = logging.getLogger(__name__)

async def get_user_tier(session: AsyncSession, telegram_id: int) -> str:
    user = await session.get(User, telegram_id)
    if not user:
        user = User(telegram_id=telegram_id, tier="free")
        session.add(user)
        await session.commit()
        return "free"
        
    if user.tier == "pro" and user.pro_expires_at and user.pro_expires_at < datetime.utcnow():
        user.tier = "free"
        await session.commit()
        
    return user.tier

async def upgrade_user_to_pro(session: AsyncSession, telegram_id: int, days: int = 30):
    user = await session.get(User, telegram_id)
    if user:
        user.tier = "pro"
        user.pro_expires_at = datetime.utcnow() + timedelta(days=days)
        await session.commit()


async def downgrade_expired_pro_users(session: AsyncSession) -> int:
    """Снимает PRO-статус и отключает лишние таски у просроченных аккаунтов."""
    query = select(User).where(
        User.tier == "pro",
        User.pro_expires_at <= func.now()
    )
    result = await session.execute(query)
    expired_users = result.scalars().all()

    if not expired_users:
        return 0

    downgraded_count = 0
    for user in expired_users:
        user.tier = "free"
        user.pro_expires_at = None
        
        # Получаем все активные задачи юзера, сортируем по дате создания
        tasks_query = select(SearchTask).where(
            SearchTask.user_id == user.telegram_id,
            SearchTask.is_active == True
        ).order_by(SearchTask.created_at.asc())
        
        tasks_result = await session.execute(tasks_query)
        active_tasks = tasks_result.scalars().all()
        
        # Оставляем первые 2 задачи, остальные глушим
        if len(active_tasks) > 2:
            for task in active_tasks[2:]:
                task.is_active = False
        
        downgraded_count += 1
        
    try:
        await session.commit()
    except Exception as e:
        logger.error(f"Error downgrading users: {e}")
        await session.rollback()
        
    return downgraded_count