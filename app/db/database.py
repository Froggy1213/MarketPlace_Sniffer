from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=10,         # Базовое количество соединений
    max_overflow=20,      # Доп. соединения на случай пиковой нагрузки
    pool_recycle=3600     # Рестарт соединений раз в час, чтобы не отваливались по таймауту
)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass