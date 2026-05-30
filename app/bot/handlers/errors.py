import logging
from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

error_router = Router()

@error_router.errors()
async def global_error_handler(event: ErrorEvent):
    """
    Global handler for all unhandled exceptions in bot handlers.
    Logs the error and sends a user-friendly notification.
    """
    # 1. Log the error with full traceback for debugging
    logger.critical(f"🔥 Critical error: {event.exception}", exc_info=True)
    
    update = event.update
    
    # 2. Try to apologize to the user
    try:
        error_msg = (
            "⚠️ <b>Oops! An internal error occurred.</b>\n"
            "Something went wrong. The developers have been notified and will fix it."
        )
        
        if update.message:
            await update.message.answer(error_msg, parse_mode="HTML")
        elif update.callback_query:
            # If user clicked a button, answer the message and cancel the loading spinner
            await update.callback_query.message.answer(error_msg, parse_mode="HTML")
            await update.callback_query.answer("An error occurred ⚙️", show_alert=True)
            
    except Exception as e:
        # If the bot couldn't even apologize (for example, the user blocked us)
        logger.error(f"Failed to send error notification to user: {e}")
    
    # 3. Always return True.
    # This signals to Aiogram: "Error is handled, no need to crash the application".
    return True