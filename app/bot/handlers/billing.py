from aiogram import Router, F
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.users import upgrade_user_to_pro

billing_router = Router()

async def send_pro_invoice(message: Message):
    prices = [LabeledPrice(label="Pro Sniper (30 days)", amount=500)] 
    
    await message.answer_invoice(
        title="⭐️ PRO Sniper",
        description="Unlock up to 30 search tasks and maximum marketplace checking speed.",
        payload="pro_30_days",
        provider_token="",  
        currency="XTR",  
        prices=prices
    )

@billing_router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@billing_router.message(F.successful_payment)
async def process_successful_payment(message: Message, session: AsyncSession):
    if not message.from_user:
        return
    
    await upgrade_user_to_pro(session, message.from_user.id, days=30)
    
    await message.answer(
        "🎉 <b>Payment processed successfully!</b>\n\n"
        "Your account has been upgraded to <b>PRO</b> level. Limits removed, "
        "worker set to priority queue mode.\n"
        "Use /add to add new search tasks.",
        parse_mode="HTML"
    )