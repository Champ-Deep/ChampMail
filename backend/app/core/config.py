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

    # Security
    webhook_secret: str = ""  # HMAC secret for webhook signature verification
    frontend_url: str = "http://localhost:3000"  # Frontend URL for CORS

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

    # AI Configuration - ALL models via OpenRouter
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Model selection (all via OpenRouter)
    research_model: str = "perplexity/sonar-pro"
    segmentation_model: str = "anthropic/claude-sonnet-4-20250514"
    pitch_model: str = "anthropic/claude-sonnet-4-20250514"
    html_model: str = "anthropic/claude-sonnet-4-20250514"
    general_model: str = "anthropic/claude-sonnet-4-20250514"
    embedding_model: str = "openai/text-embedding-3-small"

    # Research caching
    research_cache_ttl_days: int = 30
    research_batch_size: int = 50

    # Rate limiting for OpenRouter
    openrouter_rate_limit: int = 10
    openrouter_timeout: int = 120

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

    def validate_production_settings(self) -> None:
        """
        Validate critical settings for production deployment.
        Raises ValueError if any critical settings are using default/insecure values.
        """
        if self.environment == "production":
            errors = []

            # Check JWT secret
            if self.jwt_secret_key == "your-secret-key-change-in-production":
                errors.append("JWT_SECRET_KEY must be changed from default value in production")

            if len(self.jwt_secret_key) < 32:
                errors.append("JWT_SECRET_KEY must be at least 32 characters long")

            # Check database password
            if not self.postgres_password or self.postgres_password == "champmail_dev":
                errors.append("POSTGRES_PASSWORD must be set to a secure value in production")

            # Check webhook secret if webhooks are used
            if not self.webhook_secret:
                errors.append("WEBHOOK_SECRET should be set for webhook signature verification in production")

            if errors:
                raise ValueError(
                    "Production configuration validation failed:\n" +
                    "\n".join(f"  - {error}" for error in errors)
                )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
