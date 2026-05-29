from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Boolean, BigInteger, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, declarative_mixin, relationship
from sqlalchemy.dialects.postgresql import ARRAY

from app.db.database import Base


@declarative_mixin
class TimestampMixin:
    """Миксин для трекинга времени создания и обновления записей."""
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

    # Связь с задачами
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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    
    keyword: Mapped[str] = mapped_column(String, index=True)
    min_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    platforms: Mapped[list[str]] = mapped_column(ARRAY(String), default=["mercari"])
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="tasks")

    def __repr__(self) -> str:
        return f"<SearchTask {self.keyword}>"


class FoundItem(Base, TimestampMixin):
    __tablename__ = "found_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("search_tasks.id", ondelete="CASCADE"))
    market_id: Mapped[str] = mapped_column(String)

    # Защита на уровне БД: один товар отправляется одному юзеру строго один раз
    __table_args__ = (
        UniqueConstraint('user_id', 'market_id', name='uq_user_market_id'),
    )