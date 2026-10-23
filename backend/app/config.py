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
    # Required in every environment: a process-local key would write credentials nobody can decrypt later.
    email_encryption_key: str = ""
    # HMAC key for /o and /c tracking tokens. Required everywhere: a blank or changing key would
    # silently invalidate every link already sent.
    tracking_secret: str = ""
    # Base URL of the client (Harbinger) that receives POST <url>/api/email/track events.
    champmail_client_url: str = ""
    # Shared with the edge Worker (X-Edge-Secret). Blank refuses every Worker callback.
    internal_events_secret: str = ""

    # Cloudflare DNS automation: off unless the token is set. The Worker hostname is the target of
    # each domain's proxied track.<domain> CNAME; the script name is what the per-zone route runs.
    cloudflare_api_token: str = ""
    edge_worker_hostname: str = ""
    edge_worker_script: str = "champmail-edge"
    # DMARC rua mailbox, `{brand}` is replaced by the brand id (dmarc+{brand}@x.com). Blank: no rua tag.
    dmarc_rua_address: str = ""
    # IMAP mailbox the rua address delivers to. Blank host: DMARC ingestion is skipped.
    dmarc_imap_host: str = ""
    dmarc_imap_port: int = 993
    dmarc_imap_ssl: bool = True
    dmarc_imap_user: str = ""
    dmarc_imap_password: str = ""
    dmarc_imap_folder: str = "INBOX"
    # Extra DKIM selectors to probe on every domain, comma separated, on top of each domain's own dkim_selector.
    dkim_selectors: str = ""
    # Google Postmaster Tools: the service account key JSON itself. Blank: fields stay null.
    postmaster_service_account_json: str = ""

    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = False

    inboxkit_api_key: str = ""
    inboxkit_base_url: str = ""
    inboxkit_webhook_secret: str = ""
    inboxkit_workspace_id: str = ""

    worker_interval_seconds: int = 30

    @model_validator(mode="after")
    def fail_closed_in_production(self):
        if not self.email_encryption_key.strip():
            raise ValueError("unset: EMAIL_ENCRYPTION_KEY")
        if not self.tracking_secret.strip():
            raise ValueError("unset: TRACKING_SECRET")
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
