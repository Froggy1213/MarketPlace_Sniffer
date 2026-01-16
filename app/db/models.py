from sqlalchemy import String, Integer, DateTime, func, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base
from datetime import datetime

class Product(Base):
    """Таблица найденных товаров (История)"""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    platform: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    price: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Product {self.market_id}>"

class Search(Base):
    """Таблица поисковых запросов (Подписки)"""
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Ссылка на поиск (например, https://jp.mercari.com/...)
    url: Mapped[str] = mapped_column(String, unique=True)
    
    # ID пользователя Telegram, который добавил эту ссылку
    user_id: Mapped[int] = mapped_column(Integer)
    
    # Активен ли поиск (можно поставить False, чтобы временно отключить, не удаляя)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Когда добавили
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Search {self.url}>"