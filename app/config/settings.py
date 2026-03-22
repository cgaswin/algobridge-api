from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    gemini_api_key: str = Field(...)
    leetcode_endpoint: str = Field(...)
    database_url: str = Field(
        "postgresql+asyncpg://algobridge:algobridge@localhost:5432/algobridge"
    )


settings = Settings()
