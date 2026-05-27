"""
Database Models Module

This module defines SQLAlchemy ORM models for the marketplace sniffer application.
It uses SQLAlchemy 2.0 with Python type hints and mapped columns.

Models:
    - Product: Represents marketplace items that have been found/scraped
    - SearchTask: Represents user search configurations and active monitoring tasks
    - FoundItem: Represents notifications sent to users about matching products

The models use:
- Mapped columns with type annotations for better IDE support and type checking
- Indexes on frequently queried fields for performance
- Constraints (unique, nullable) for data integrity
- Server-side defaults (func.now()) for timestamp management
"""

from sqlalchemy import Column, String, Integer, DateTime, func, Boolean, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base
from datetime import datetime
from typing import Optional

# ============================================================================
# USER MODEL - Telegram Users
# ============================================================================

class User(Base):
    """
    Represents a Telegram user who has interacted with the bot.
    
    This table is used to track users and their associated search tasks.
    It can also be used for future features like user preferences, subscription status, etc.
    
    Schema Design:
        - Primary key: user_id (Telegram user ID)
        - Indexed for fast lookups when sending notifications
        - Can store additional user info in the future (e.g., username, language)
    """
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True)
    tier = Column(String, default="free")  
    pro_expires_at = Column(DateTime, nullable=True)


# ============================================================================
# PRODUCT MODEL - Scraped Marketplace Items
# ============================================================================

class Product(Base):
    """
    Represents a single product/item found on a Japanese marketplace.
    
    This table acts as a historical record of all products we've scraped.
    It serves two purposes:
    1. Deduplication: Check if we've already seen this product (by market_id)
    2. Historical record: Track what items we've found over time
    
    The table is intentionally simple - minimal fields needed to track products.
    Full product details are stored in FoundItem table (when sent to users).
    
    Schema Design:
        - Primary key: auto-incrementing id
        - Unique constraint: market_id (prevents duplicate entries)
        - Indexes: market_id, platform (for fast lookups during deduplication)
    
    Workflow:
        1. When parser finds new items, ItemData is converted to Product
        2. Database checks if market_id already exists
        3. If new: INSERT, if duplicate: SKIP
        4. Product record persists indefinitely (historical record)
    
    Naming Note:
        The table name "products" is generic to work across all marketplaces.
        Items from Mercari, Yahoo, Rakuma, etc. all go to the same table.
    """
    __tablename__ = "products"

    # Primary key: Auto-incrementing integer ID
    # Used for internal database relationships and efficiency
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Marketplace-specific unique product identifier
    # Examples: "1234567890" (Mercari), "a1b2c3d4" (Yahoo)
    # CRITICAL FOR DEDUPLICATION: Unique constraint prevents inserting same product twice
    # Indexed for fast lookup during deduplication checks
    # Data type: String (some marketplaces use alphanumeric IDs)
    market_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    
    # Name of the source marketplace platform
    # Values: "mercari", "yahoo", "rakuma", "rakuten", "paypay"
    # Indexed for analytics and filtering by platform
    # Allows querying "how many items found on each platform"
    platform: Mapped[str] = mapped_column(String, index=True)
    
    # Product name/title as displayed on the marketplace
    # Cleaned of HTML tags and extra whitespace
    # Example: "Apple MacBook Pro 14-inch M1 2021"
    # No index needed (not typically used in WHERE clauses for deduplication)
    title: Mapped[str] = mapped_column(String)
    
    # Product price in Japanese Yen (¥)
    # Stored as integer (no decimal points)
    # Example: 50000 (meaning ¥50,000)
    # No index (filtering by price happens in SearchTask table)
    price: Mapped[int] = mapped_column(Integer)
    
    # Direct link to the product page on the marketplace
    # Complete URL that can be clicked to view the full product
    # Examples: 
    # - https://www.mercari.com/jp/items/m12345678/
    # - https://auctions.yahoo.co.jp/item/a1234567890
    url: Mapped[str] = mapped_column(String)
    
    # Timestamp when this product was first scraped/added to database
    # Automatically set by database (server_default=func.now())
    # Timezone-aware (UTC)
    # Useful for:
    # - Sorting recent finds
    # - Analytics: "How many items found today/this week?"
    # - Old record cleanup (archive records older than N days)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        """String representation for debugging and logging"""
        return f"<Product {self.market_id}>"


# ============================================================================
# SEARCH TASK MODEL - User Search Configurations
# ============================================================================

class SearchTask(Base):
    """
    Represents a user's active search task/monitoring configuration.
    
    This table stores search parameters for each user, controlling what items
    to search for, where to search, and for how long.
    
    Core Purpose:
        - Define what products to search for (keyword + price range + platforms)
        - Track which users are actively monitoring (is_active flag)
        - Enable the worker to know which searches to execute
    
    Workflow:
        1. User runs /add command in Telegram bot
        2. Bot collects: keyword, platforms, min_price, max_price
        3. Task is saved to search_tasks table with is_active=True
        4. Worker queries: SELECT * FROM search_tasks WHERE is_active=True
        5. Worker executes each task (runs parsers with task parameters)
        6. When items found, notifications sent to task owner (user_id)
        7. User can /del command to deactivate task (is_active=False or DELETE)
    
    Data Integrity:
        - Each task tied to specific user_id (multi-tenant)
        - Duplicate prevention: (user_id, keyword, platforms) combination is unique
        - Task creates search URLs dynamically (keyword + platforms + prices)
    
    Relationship:
        - Many tasks per user
        - Each task can match many FoundItems (1-to-many)
        - FoundItem.search_task_id references SearchTask.id
    
    SQL-Side Defaults:
        - is_active: defaults to True (new tasks start active)
        - platforms: defaults to "mercari,yahoo" (two most popular)
        - created_at: auto-set by database (UTC timestamp)
    """
    __tablename__ = "search_tasks"

    # Primary key: Auto-incrementing integer ID
    # Used internally for database relationships
    # Referenced by FoundItem table (FK: FoundItem.search_task_id)
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # Telegram user ID of the task owner
    # Identifies which user created this search task
    # BigInteger used because Telegram user IDs can be very large (> 2^31)
    # Indexed for fast lookup: "What searches does user X have?"
    # Used when sending notifications: "Send to user_id"
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    
    # ========================================================================
    # SEARCH PARAMETERS
    # ========================================================================
    
    # Search keyword/query term
    # Example: "MacBook", "ThinkPad X1", "PS5"
    # Indexed for analytics: "Most popular search terms"
    # Used to construct marketplace search URLs
    # Note: No exact matching - passed as-is to marketplace search engines
    keyword: Mapped[str] = mapped_column(String, index=True)
    
    # Minimum price filter in Japanese Yen (¥)
    # Optional: If None/NULL, no minimum price filter
    # Example: 10000 means only show items ≥ ¥10,000
    # Can be NULL if user doesn't want minimum (allows all prices)
    # Used in parser: price >= min_price
    min_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Maximum price filter in Japanese Yen (¥)
    # Optional: If None/NULL, no maximum price filter
    # Example: 100000 means only show items ≤ ¥100,000
    # Can be NULL if user doesn't want maximum (allows all prices)
    # Used in parser: price <= max_price
    max_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Comma-separated list of marketplace platforms to search
    # Format: "platform1,platform2,..." (lowercase, no spaces)
    # Example: "mercari,yahoo" or "mercari,yahoo,rakuten"
    # Supported platforms: mercari, yahoo, rakuma, rakuten, paypay
    # Default: "mercari,yahoo" (two most popular marketplaces)
    # Used by worker to determine which parsers to run for this task
    # Parser searches URLs like: mercari.com?q=keyword vs yahoo.co.jp?q=keyword
    platforms: Mapped[str] = mapped_column(String, default="mercari,yahoo")
    
    # ========================================================================
    # TASK CONTROL
    # ========================================================================
    
    # Boolean flag indicating if this task is currently active
    # True: Worker will execute this task regularly
    # False: Task is paused/disabled (worker skips it)
    # Default: True (new tasks start active)
    # Usage: User /del command sets this to False (soft delete)
    # Alternative: Could use is_active=False or actual DELETE
    # Indexed if we query "active tasks" frequently
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Timestamp when this task was created
    # Automatically set by database (server_default=func.now())
    # Timezone-aware (UTC)
    # Useful for:
    # - Sorting recently created tasks
    # - Analytics: "How many new searches today?"
    # - Task aging: "Identify stale searches"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        """String representation for debugging and logging"""
        return f"<SearchTask {self.keyword}>"

