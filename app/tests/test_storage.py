import asyncio
from app.services.parser_service import ItemData
from app.services.storage import save_new_items

async def main():
    # 1. Создаем фейковые данные (как будто от парсера)
    fake_items = [
        ItemData(market_id="m111", title="Test Item 1", price=1000, url="http://url1", platform="mercari"),
        ItemData(market_id="m222", title="Test Item 2", price=2000, url="http://url2", platform="mercari"),
        ItemData(market_id="m333", title="Test Item 3", price=3000, url="http://url3", platform="mercari"),
    ]

    print("--- ПОПЫТКА 1 (База пустая) ---")
    new_ones = await save_new_items(fake_items)
    print(f"🆕 Вернулось новых товаров: {len(new_ones)} (Ожидаем 3)")

    print("\n--- ПОПЫТКА 2 (Те же товары) ---")
    new_ones_again = await save_new_items(fake_items)
    print(f"🆕 Вернулось новых товаров: {len(new_ones_again)} (Ожидаем 0)")
    
    print("\n--- ПОПЫТКА 3 (Появился один новый) ---")
    mixed_items = fake_items + [
        ItemData(market_id="m444", title="NEW RARE ITEM", price=9999, url="http://url4", platform="mercari")
    ]
    final_batch = await save_new_items(mixed_items)
    print(f"🆕 Вернулось новых товаров: {len(final_batch)} (Ожидаем 1)")
    
    if final_batch:
        print(f"Имя нового товара: {final_batch[0].title}")

if __name__ == "__main__":
    asyncio.run(main())