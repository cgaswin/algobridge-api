from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    gemini_api_key: str = Field(...)
    gemini_model: str = Field("gemini-3-flash-preview")
    ai_daily_generation_limit: int = Field(100, ge=0)
    ai_generation_timeout_seconds: float = Field(30.0, gt=0, le=300)
    leetcode_graphql_url: str = Field("https://leetcode.com/graphql/")
    database_url: str = Field(
        "postgresql+asyncpg://algobridge:algobridge@localhost:5432/algobridge"
    )


settings = Settings()
