from sqlalchemy import String, Integer, DateTime, func, Boolean, BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, declarative_mixin, relationship
from sqlalchemy.dialects.postgresql import ARRAY
from app.db.database import Base
from datetime import datetime
from typing import Optional

@declarative_mixin
class TimestampMixin:
    """Миксин для автоматического трекинга времени создания и обновления записей."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now()
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tier: Mapped[str] = mapped_column(String, default="free")  
    pro_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Двусторонняя связь для удобной выборки: user.tasks
    tasks: Mapped[list["SearchTask"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    platform: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    price: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String)

    def __repr__(self) -> str:
        return f"<Product {self.platform}:{self.market_id}>"


class SearchTask(Base, TimestampMixin):
    __tablename__ = "search_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Внешний ключ: при удалении юзера, его задачи удалятся каскадно
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    
    keyword: Mapped[str] = mapped_column(String, index=True)
    min_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Используем ARRAY для PostgreSQL. Теперь можно делать правильные фильтры в БД
    platforms: Mapped[list[str]] = mapped_column(ARRAY(String), default=lambda: ["mercari", "yahoo"])
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Связь с таблицей пользователей
    user: Mapped["User"] = relationship(back_populates="tasks")

    def __repr__(self) -> str:
        return f"<SearchTask {self.keyword}>"