from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings

# No models yet: M1 sets target_metadata when the first tables land.
target_metadata = None
url = get_settings().database_url

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
