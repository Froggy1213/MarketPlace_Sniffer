from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from app.services.storage import add_search_url, get_all_searches, delete_search_by_id
from app.core.config import settings

# Роутер — это как "перекресток", который направляет сообщения нужным функциям
router = Router()

# Проверка, что пишет Админ (ты), а не посторонний
def is_admin(user_id: int) -> bool:
    return user_id == settings.ADMIN_ID

@router.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer(
        "👋 <b>Привет, Охотник!</b>\n\n"
        "Я готов искать товары.\n"
        "Команды:\n"
        "➕ <code>/add ссылка</code> — Добавить поиск\n"
        "📋 <code>/list</code> — Список активных поисков\n"
        "🗑 <code>/del ID</code> — Удалить поиск",
        parse_mode="HTML"
    )

@router.message(Command("add"))
async def cmd_add(message: Message):
    if not is_admin(message.from_user.id): return
    
    # Разбиваем сообщение "/add https://..." на части
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("⚠️ Ошибка. Используй: <code>/add https://mercari...</code>", parse_mode="HTML")
        return

    url = parts[1].strip()
    # Простейшая валидация
    if "mercari.com" not in url and "yahoo.co.jp" not in url:
        await message.answer("⛔ Я понимаю только ссылки Mercari и Yahoo Auctions.")
        return

    success = await add_search_url(url, message.from_user.id)
    if success:
        await message.answer(f"✅ <b>Ссылка добавлена!</b>\nСкоро начну мониторить.", parse_mode="HTML")
    else:
        await message.answer("⚠️ Эта ссылка уже есть в списке.")

@router.message(Command("list"))
async def cmd_list(message: Message):
    if not is_admin(message.from_user.id): return
    
    searches = await get_all_searches()
    if not searches:
        await message.answer("📭 Список пуст.")
        return

    text = "<b>📋 Активные поиски:</b>\n\n"
    for s in searches:
        # Обрезаем длинную ссылку для красоты
        short_url = s.url[:40] + "..." if len(s.url) > 40 else s.url
        text += f"🔹 <b>ID: {s.id}</b> | <a href='{s.url}'>Ссылка</a>\n"
    
    text += "\nЧтобы удалить: <code>/del ID</code>"
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

@router.message(Command("del"))
async def cmd_del(message: Message):
    if not is_admin(message.from_user.id): return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("⚠️ Используй: <code>/del ID</code> (ID смотри в /list)", parse_mode="HTML")
        return

    search_id = int(parts[1])
    success = await delete_search_by_id(search_id)
    
    if success:
        await message.answer(f"🗑 Поиск <b>ID {search_id}</b> удален.", parse_mode="HTML")
    else:
        await message.answer("❌ Не нашел такой ID.")