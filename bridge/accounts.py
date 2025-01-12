from aiogram import Bot
from signalbot import SignalBot

from bridge.core.config import settings


signal = SignalBot(
    {
        'signal_service': settings.SIGNAL_API_HOST.get_secret_value(),
        'phone_number': settings.SIGNAL_PHONE_NUMBER.get_secret_value(),
    }
)
telegram = Bot(token=settings.TELEGRAM_TOKEN.get_secret_value())
