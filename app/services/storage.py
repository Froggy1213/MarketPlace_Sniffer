"""
Storage module for database operations related to products, search tasks, and found items.

This module provides async functions to interact with the database:
- Product management: saving new items found on marketplaces
- Search task management: creating, retrieving, and deleting user search tasks
- System statistics: collecting metrics about active tasks and found items
"""

import logging
from typing import List, Optional
from sqlalchemy import select, delete, func
from app.db.database import async_session_maker
from app.db.models import Product, SearchTask, FoundItem, User
from app.services.parsers.base import ItemData
from datetime import datetime, timedelta
from sqlalchemy import select, delete, func

# Logger instance for this module
logger = logging.getLogger(__name__)


async def get_user_tier(telegram_id: int) -> str:
    """Возвращает текущий тариф пользователя (создает его, если он новый)."""
    async with async_session_maker() as session:
        user = await session.get(User, telegram_id)
        if not user:
            user = User(telegram_id=telegram_id, tier="free")
            session.add(user)
            await session.commit()
            return "free"
            
        # Проверяем, не истекла ли подписка
        if user.tier == "pro" and user.pro_expires_at and user.pro_expires_at < datetime.utcnow():
            user.tier = "free"
            await session.commit()
            
        return user.tier

async def count_user_tasks(telegram_id: int) -> int:
    """Считает активные задачи пользователя."""
    async with async_session_maker() as session:
        query = select(func.count(SearchTask.id)).where(
            SearchTask.user_id == telegram_id, 
            SearchTask.is_active == True
        )
        return await session.scalar(query) or 0

async def upgrade_user_to_pro(telegram_id: int, days: int = 30):
    """Активирует PRO-тариф."""
    async with async_session_maker() as session:
        user = await session.get(User, telegram_id)
        if user:
            user.tier = "pro"
            user.pro_expires_at = datetime.utcnow() + timedelta(days=days)
            await session.commit()


# ============================================================================
# SYSTEM STATISTICS FUNCTIONS
# ============================================================================
# Functions for collecting and reporting system metrics about the crawler

async def get_system_stats() -> dict:
    """
    Collects system statistics without loading all data into memory.
    
    This function uses SQL COUNT aggregates for efficient metric collection,
    suitable for displaying in dashboard or admin panels.
    
    Returns:
        dict: Contains:
            - 'active_tasks': Number of currently active search tasks
            - 'total_found_items': Total number of products found across all tasks
    
    Note: Uses COUNT queries for performance efficiency instead of loading full datasets.
    """
    async with async_session_maker() as session:
        # Query to count all active search tasks (where is_active == True)
        active_tasks_query = select(func.count(SearchTask.id)).where(SearchTask.is_active == True)
        active_tasks = await session.scalar(active_tasks_query)

        # Query to count the total number of found items in the database
        found_items_query = select(func.count(FoundItem.id))
        total_items = await session.scalar(found_items_query)

        return {
            "active_tasks": active_tasks or 0,
            "total_found_items": total_items or 0
        }


# ============================================================================
# PRODUCT MANAGEMENT FUNCTIONS
# ============================================================================
# Functions for saving and managing product data fetched from various marketplaces

async def save_new_items(items: List[ItemData]) -> List[ItemData]:
    """
    Saves new products to the database and returns only those that were newly created.
    
    This function filters out duplicate products (those already in the database)
    and only saves new ones. This prevents duplicate entries and avoids unnecessary
    database operations for items we're already tracking.
    
    Args:
        items (List[ItemData]): List of item data objects from marketplace parsers.
                               Each item contains market_id, platform, title, price, url.
    
    Returns:
        List[ItemData]: Only the items that were newly saved to the database.
                       Duplicate items are filtered out and not returned.
    
    Workflow:
        1. Extract market IDs from all incoming items
        2. Query database to find which market IDs already exist
        3. Filter items: only keep those with new market IDs
        4. Insert the new products into the database
        5. Return the list of newly saved items
    """
    if not items:
        # Early return for empty input to avoid unnecessary database operations
        return []

    async with async_session_maker() as session:
        # Extract market_id values from all items for batch duplicate checking
        market_ids = [item.market_id for item in items]

        # Query the database to find which of these market_ids already exist
        # This is more efficient than checking each item individually
        query = select(Product.market_id).where(Product.market_id.in_(market_ids))
        result = await session.execute(query)
        # Store existing market IDs in a set for O(1) lookup time
        existing_ids = set(row[0] for row in result.all())

        # Lists to store new items and products
        new_items_data = []
        new_products_to_insert = []

        # Process each item and filter for duplicates
        for item in items:
            if item.market_id not in existing_ids:
                # This is a new item, add it to both lists
                new_items_data.append(item)
                
                # Create a Product model instance from the ItemData
                product_model = Product(
                    market_id=item.market_id,
                    platform=item.platform,
                    title=item.title,
                    price=item.price,
                    url=item.url
                )
                new_products_to_insert.append(product_model)
                # Add to existing_ids to prevent duplicates within this batch
                existing_ids.add(item.market_id)

        # Only perform database operation if there are new products
        if new_products_to_insert:
            try:
                # Add all new products to the session
                session.add_all(new_products_to_insert)
                # Commit the transaction
                await session.commit()
                logger.info(f"💾 New products saved to DB: {len(new_products_to_insert)}")
            except Exception as e:
                logger.error(f"Error saving products: {e}")
                # Rollback changes if an error occurs
                await session.rollback()

        # Return only the newly saved items (duplicates not included)
        return new_items_data


# ============================================================================
# SEARCH TASK MANAGEMENT FUNCTIONS
# ============================================================================
# Functions for managing user search tasks (create, retrieve, delete)

async def add_search_task(
        user_id: int,
        keyword: str,
        platforms: str,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None
) -> bool:
    """
    Adds a new search task to the database for a user.
    
    This function prevents users from creating duplicate search tasks by checking
    if they're already searching for the same keyword and platforms combination.
    
    Args:
        user_id (int): Telegram user ID
        keyword (str): Search keyword/term
        platforms (str): Comma-separated list of marketplace platforms to search
        min_price (Optional[int]): Minimum price filter (if specified)
        max_price (Optional[int]): Maximum price filter (if specified)
    
    Returns:
        bool: True if task was successfully created, False if duplicate or error occurred
    
    Security Note:
        Each task is tied to a specific user_id to ensure users can only see
        and manage their own searches.
    """
    async with async_session_maker() as session:
        # Duplicate guard: check if user already has this exact search task
        # Prevents users from creating redundant tasks
        query = select(SearchTask).where(
            SearchTask.user_id == user_id,
            SearchTask.keyword == keyword,
            SearchTask.platforms == platforms
        )
        result = await session.execute(query)
        # If an identical task exists, return False
        if result.scalar_one_or_none():
            return False

        try:
            # Create a new SearchTask object with provided parameters
            new_task = SearchTask(
                user_id=user_id,
                keyword=keyword,
                platforms=platforms,
                min_price=min_price,
                max_price=max_price
            )
            # Add the new task to the session
            session.add(new_task)
            # Commit the transaction to persist the task
            await session.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding task: {e}")
            # Rollback in case of database error
            await session.rollback()
            return False


async def get_all_active_tasks() -> List[SearchTask]:
    """
    Fetches all active search tasks from the database.
    
    This function is used by the background worker to retrieve all tasks
    that need to be executed in this cycle.
    
    Returns:
        List[SearchTask]: List of all active search tasks from all users.
                         Only tasks with is_active=True are returned.
    
    Usage:
        Called by the Celery worker to get tasks for parallel execution.
    """
    async with async_session_maker() as session:
        # Query database for all tasks where is_active is True
        result = await session.execute(select(SearchTask).where(SearchTask.is_active))
        # Return as a list
        return list(result.scalars().all())


async def get_user_tasks(user_id: int) -> List[SearchTask]:
    """
    Fetches all active search tasks for a specific user.
    
    This function is used by the Telegram bot to display the user's search list
    when they request the /list command.
    
    Args:
        user_id (int): Telegram user ID to fetch tasks for
    
    Returns:
        List[SearchTask]: List of all active search tasks belonging to this user.
                         Includes metadata like keywords, platforms, price filters.
    
    Usage:
        Called when user executes /list command to see their active searches.
    """
    async with async_session_maker() as session:
        # Query database for all active tasks (is_active == True)
        result = await session.execute(select(SearchTask).where(SearchTask.is_active.is_(True)))
        # Return as a list
        return list(result.scalars().all())


async def delete_search_task(task_id: int, user_id: int) -> bool:
    """
    Deletes a search task from the database.
    
    Important security feature: This function requires both task_id AND user_id
    to prevent users from deleting other users' search tasks. A user can only
    delete tasks that belong to them.
    
    Args:
        task_id (int): ID of the search task to delete
        user_id (int): Telegram user ID (must match the task owner)
    
    Returns:
        bool: True if task was successfully deleted, False if task not found or error occurred
    
    Security:
        The query checks both task_id AND user_id, so a user cannot delete
        another user's task even if they know the task_id.
    
    Note:
        This function uses soft deletes by setting is_active=False rather than
        removing records from the database.
    """
    async with async_session_maker() as session:
        try:
            # Build delete statement with both task_id and user_id constraints
            # This ensures users can only delete their own tasks
            stmt = delete(SearchTask).where(
                SearchTask.id == task_id,
                SearchTask.user_id == user_id
            )
            # Execute the delete statement
            result = await session.execute(stmt)
            # Commit the transaction
            await session.commit()
            # Return True if at least one row was deleted, False otherwise
            return result.rowcount > 0 # type: ignore
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            # Rollback changes if an error occurs
            await session.rollback()
            return False