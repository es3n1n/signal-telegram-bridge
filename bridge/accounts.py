from dataclasses import dataclass
from functools import lru_cache

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
telegram_bots_for_signal_users: dict[str, Bot] = {
    k: Bot(token=v.get_secret_value()) for k, v in settings.TELEGRAM_PERSONALIZED_TOKENS.items()
}


@dataclass(frozen=True)
class PersonalizedBot:
    is_personalized: bool
    bot: Bot


@lru_cache(maxsize=32)
def bot_for_signal_user(user_id: str) -> PersonalizedBot:
    result: Bot | None = telegram_bots_for_signal_users.get(user_id)
    if not result:
        return PersonalizedBot(is_personalized=False, bot=telegram)

    return PersonalizedBot(is_personalized=True, bot=result)
