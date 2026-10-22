"""SQLAlchemy models for PostgreSQL persistence."""
from app.models.domain import Domain
from app.models.email_account import EmailAccount

__all__ = ["Domain", "EmailAccount"]