"""Billing and payment handlers for PRO subscription.

This module handles invoice generation, payment processing via Telegram Stars,
and user account upgrades to PRO tier.
"""
from aiogram import Router, F
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery

from app.services.storage import upgrade_user_to_pro

# Router for billing-related message and payment handlers
billing_router = Router()


async def send_pro_invoice(message: Message):
    """Send payment invoice for PRO subscription via Telegram Stars.
    
    Args:
        message: The Telegram message object to send invoice to.
    """
    # Create price list for 30-day PRO subscription (500 stars)
    prices = [LabeledPrice(label="Pro Sniper (30 days)", amount=500)] 
    
    # Send invoice to user
    await message.answer_invoice(
        title="⭐️ PRO Sniper",
        description="Unlock up to 30 search tasks and maximum marketplace checking speed.",
        payload="pro_30_days",
        provider_token="",  # Telegram Stars requires no provider token
        currency="XTR",  # XTR is Telegram Stars currency
        prices=prices
    )


@billing_router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Validate payment before processing.
    
    Confirms the payment to Telegram to proceed with charging.
    """
    # Always confirm pre-checkout query for valid payments
    await pre_checkout_query.answer(ok=True)


@billing_router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Handle successful payment and upgrade user to PRO.
    
    Updates user tier in database and notifies user about upgrade.
    """
    # Validate message and user
    if not message.from_user:
        return
    
    # Upgrade user to PRO tier for 30 days
    await upgrade_user_to_pro(message.from_user.id, days=30)
    
    # Send confirmation message to user
    await message.answer(
        "🎉 <b>Payment processed successfully!</b>\n\n"
        "Your account has been upgraded to <b>PRO</b> level. Limits removed, "
        "worker set to priority queue mode.\n"
        "Use /add to add new search tasks.",
        parse_mode="HTML"
    )