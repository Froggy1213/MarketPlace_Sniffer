from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User

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