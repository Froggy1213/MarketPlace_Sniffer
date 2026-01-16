import asyncio
from app.db.database import engine, Base
from app.db.models import Product


async def init_models():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.create_all)

        print("creating tables in DB...")
        await conn.run_sync(Base.metadata.create_all)
        print("Done!")


if __name__ == '__main__':
    asyncio.run(init_models())