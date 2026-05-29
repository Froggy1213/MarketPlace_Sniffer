from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

# Движок для бота (Использует дефолтный асинхронный пул, просто задаем лимиты)
bot_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    echo=False
)

# Движок для Celery (Выключаем пулинг, чтобы не ловить InterfaceError при форках)
worker_engine = create_async_engine(
    settings.DATABASE_URL,
    poolclass=NullPool,
    echo=False
)

# Фабрики сессий
bot_session_maker = async_sessionmaker(bot_engine, expire_on_commit=False, class_=AsyncSession)
worker_session_maker = async_sessionmaker(worker_engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass