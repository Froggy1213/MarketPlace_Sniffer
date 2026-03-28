from sqlalchemy import String, Integer, DateTime, func, Boolean, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base
from datetime import datetime
from typing import Optional

class Product(Base):
    """History"""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    platform: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    price: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Product {self.market_id}>"

class SearchTask(Base):
    """Search Task"""
    __tablename__ = "search_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    # Параметры поиска
    keyword: Mapped[str] = mapped_column(String, index=True)
    min_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    platforms: Mapped[str] = mapped_column(String, default="mercari,yahoo")
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<SearchTask {self.keyword}>"