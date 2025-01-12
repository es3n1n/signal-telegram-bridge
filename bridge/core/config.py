from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', case_sensitive=True)

    # Signal configuration
    SIGNAL_PHONE_NUMBER: SecretStr
    SIGNAL_CLI_PATH: Path
    SIGNAL_API_HOST: SecretStr = SecretStr('127.0.0.1:8080')
    SIGNAL_CHATS: list[str]

    # Telegram configuration
    TELEGRAM_TOKEN: SecretStr
    TELEGRAM_CHATS: list[int]

    # signal user id: bot token
    TELEGRAM_PERSONALIZED_TOKENS: dict[str, SecretStr] = Field(default_factory=dict)

    @classmethod
    def load(cls) -> Self:
        return cls()  # type: ignore[call-arg]


settings = Settings.load()
