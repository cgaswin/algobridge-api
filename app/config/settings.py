from ipaddress import ip_network

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Positive values only: invalid limits fail startup rather than disable protection.
    rate_limit_requests: int = Field(60, gt=0)
    rate_limit_window_seconds: int = Field(60, gt=0)
    rate_limit_max_ips: int = Field(10_000, gt=0)
    # Uvicorn reads this from the process environment, not this Settings object.
    forwarded_allow_ips: str = ""

    @field_validator("forwarded_allow_ips")
    @classmethod
    def validate_trusted_proxies(cls, value: str) -> str:
        if value:
            for host in value.split(","):
                network = ip_network(host.strip())
                if network.prefixlen == 0:
                    raise ValueError(
                        "Trust specific proxy IPs/CIDRs, not all addresses"
                    )
        return value

    gemini_api_key: str = Field(...)
    gemini_model: str = Field("gemini-3-flash-preview")
    leetcode_graphql_url: str = Field("https://leetcode.com/graphql/")
    database_url: str = Field(
        "postgresql+asyncpg://algobridge:algobridge@localhost:5432/algobridge"
    )


settings = Settings()
