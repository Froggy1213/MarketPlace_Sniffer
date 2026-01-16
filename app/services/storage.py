import logging
from typing import List, Optional
from sqlalchemy import select, delete
from app.db.database import async_session_maker
from app.db.models import Product, Search
from app.services.parser_service import ItemData

logger = logging.getLogger(__name__)

# --- РАБОТА С ТОВАРАМИ (То, что уже было) ---

async def save_new_items(items: List[ItemData]) -> List[ItemData]:
    """Сохраняет новые товары и возвращает их список"""
    if not items:
        return []

    async with async_session_maker() as session:
        market_ids = [item.market_id for item in items]
        
        # Проверяем дубли
        query = select(Product.market_id).where(Product.market_id.in_(market_ids))
        result = await session.execute(query)
        existing_ids = set(row[0] for row in result.all())
        
        new_items_data = []
        new_products_to_insert = []
        
        for item in items:
            if item.market_id not in existing_ids:
                new_items_data.append(item)
                product_model = Product(
                    market_id=item.market_id,
                    platform=item.platform,
                    title=item.title,
                    price=item.price,
                    url=item.url
                )
                new_products_to_insert.append(product_model)
                existing_ids.add(item.market_id)

        if new_products_to_insert:
            try:
                session.add_all(new_products_to_insert)
                await session.commit()
                logger.info(f"💾 Сохранено новых товаров в БД: {len(new_products_to_insert)}")
            except Exception as e:
                logger.error(f"Ошибка сохранения товаров: {e}")
                await session.rollback()
        
        return new_items_data

# --- РАБОТА С ПОИСКОМ (Новое) ---

async def add_search_url(url: str, user_id: int) -> bool:
    """Добавляет новую ссылку в базу"""
    async with async_session_maker() as session:
        # Проверяем, есть ли уже такая ссылка
        result = await session.execute(select(Search).where(Search.url == url))
        if result.scalar_one_or_none():
            return False # Уже есть

        try:
            new_search = Search(url=url, user_id=user_id)
            session.add(new_search)
            await session.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления ссылки: {e}")
            await session.rollback()
            return False

async def get_all_searches() -> List[Search]:
    """Получает все активные поиски (для списка команд и для парсера)"""
    async with async_session_maker() as session:
        result = await session.execute(select(Search).where(Search.is_active == True))
        return list(result.scalars().all())

async def delete_search_by_id(search_id: int) -> bool:
    """Удаляет поиск по ID"""
    async with async_session_maker() as session:
        try:
            stmt = delete(Search).where(Search.id == search_id)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка удаления ссылки: {e}")
            await session.rollback()
            return False