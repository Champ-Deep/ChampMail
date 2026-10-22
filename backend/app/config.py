from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Secrets come from the process environment only: no .env file is read here.
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    champmail_env: str = "development"
    database_url: str = "postgresql+psycopg://champmail:champmail@postgres:5432/champmail"
    redis_url: str = "redis://redis:6379/0"
    champmail_api_key: str = ""
    champmail_webhook_secret: str = ""

    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False

    inboxkit_api_key: str = ""
    inboxkit_base_url: str = ""
    inboxkit_webhook_secret: str = ""

    worker_interval_seconds: int = 30

    @model_validator(mode="after")
    def fail_closed_in_production(self):
        if self.champmail_env.strip().lower() in ("production", "prod"):
            missing = [
                n
                for n in ("champmail_api_key", "champmail_webhook_secret")
                if not getattr(self, n).strip()
            ]
            if missing:
                raise ValueError(f"unset in production: {', '.join(n.upper() for n in missing)}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
