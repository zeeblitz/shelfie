"""Configuration module using Pydantic Settings."""

from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Discord Configuration
    DISCORD_TOKEN: SecretStr = Field(..., description="Discord bot token")

    # MongoDB Configuration
    MONGODB_URI: str = Field(..., description="MongoDB connection string")
    MONGODB_DB_NAME: str = Field(default="shelfie", description="Database name")

    # Google Books API
    GOOGLE_BOOKS_API_KEY: Optional[str] = Field(
        default=None, description="Google Books API key (optional)"
    )

    # Application Settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    CACHE_TTL_SECONDS: int = Field(default=3600, description="Cache TTL in seconds")
    FEED_RATE_LIMIT_SECONDS: int = Field(
        default=3600, description="Rate limit for feed posts in seconds"
    )

    # Health Check Server
    HEALTH_HOST: str = Field(default="0.0.0.0", description="Health check host")
    HEALTH_PORT: int = Field(default=8080, description="Health check port")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the global settings instance."""
    global settings
    if settings is None:
        settings = Settings()
    return settings