import logging
from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

error_router = Router()

@error_router.errors()
async def global_error_handler(event: ErrorEvent):
    """
    Глобальный перехватчик всех необработанных исключений в хендлерах бота.
    """
    # 1. Логируем саму ошибку с полным трейсбеком для отладки
    logger.critical(f"🔥 Критическая ошибка: {event.exception}", exc_info=True)
    
    update = event.update
    
    # 2. Пытаемся извиниться перед пользователем
    try:
        error_msg = (
            "⚠️ <b>Упс! Произошла внутренняя ошибка.</b>\n"
            "Что-то пошло не так. Разработчики уже получили уведомление и всё починят."
        )
        
        if update.message:
            await update.message.answer(error_msg, parse_mode="HTML")
        elif update.callback_query:
            # Если юзер нажал кнопку, отвечаем на сообщение с кнопкой и гасим "часики" загрузки
            await update.callback_query.message.answer(error_msg, parse_mode="HTML")
            await update.callback_query.answer("Произошла ошибка ⚙️", show_alert=True)
            
    except Exception as e:
        # Если бот даже извиниться не смог (например, юзер нас заблокировал)
        logger.error(f"Не удалось отправить уведомление об ошибке юзеру: {e}")
    
    # 3. Обязательно возвращаем True. 
    # Это сигнал для Aiogram: "Ошибка обработана, не нужно крашить приложение".
    return True