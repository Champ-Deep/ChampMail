"""
Application configuration using Pydantic Settings.
Loads from environment variables and .env file.
"""

from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "ChampMail"
    app_version: str = "0.1.0"
    debug: bool = True
    environment: str = "development"

    # API
    api_v1_prefix: str = "/api/v1"

    # FalkorDB
    falkordb_host: str = "localhost"
    falkordb_port: int = 6379
    falkordb_password: str = ""
    falkordb_database: str = "champions_email_engine"

    # Redis Cache
    redis_host: str = "localhost"
    redis_port: int = 6380
    redis_password: str = ""
    redis_db: int = 0

    # PostgreSQL (User Management)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "champmail"
    postgres_password: str = "champmail_dev"
    postgres_db: str = "champmail"

    # JWT Authentication
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours

    # ChampMail Internal Mail Server (Stalwart-based)
    # SMTP (Outbound Email)
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    mail_from_email: str = "noreply@champmail.dev"
    mail_from_name: str = "ChampMail"

    # IMAP (Inbound/Reply Detection)
    imap_host: str = "localhost"
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_use_ssl: bool = True
    imap_mailbox: str = "INBOX"
    imap_check_interval: int = 60  # seconds

    # n8n Integration
    # Default to Railway instance; override with N8N_WEBHOOK_URL env var
    n8n_webhook_url: str = "https://championtest.up.railway.app/webhook"
    n8n_api_key: str = ""

    # AI Configuration
    # Text Generation (Brain)
    ai_provider: str = "anthropic"  # "openai" or "anthropic"
    ai_model: str = "claude-3-5-sonnet-latest"
    anthropic_api_key: str = ""
    
    # Embeddings (Knowledge Graph)
    embedding_provider: str = "openai"  # "openai" or "gemini"
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # External APIs
    lake_b2b_api_key: str = ""
    lake_b2b_api_url: str = "https://api.lakeb2b.com"

    @property
    def falkordb_url(self) -> str:
        """Build FalkorDB connection URL."""
        if self.falkordb_password:
            return f"redis://:{self.falkordb_password}@{self.falkordb_host}:{self.falkordb_port}"
        return f"redis://{self.falkordb_host}:{self.falkordb_port}"

    @property
    def redis_url(self) -> str:
        """Build Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def postgres_url(self) -> str:
        """Build PostgreSQL async connection URL."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
