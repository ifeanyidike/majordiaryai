from logging.config import fileConfig
from urllib.parse import quote_plus
from sqlalchemy import create_engine, pool
from alembic import context
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import effective_db_port, settings
from app.models.base import Base
import app.models.models  # noqa: F401 — registers all ORM models

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Build sync URL manually — avoids configparser % interpolation issues.
# effective_db_port() is shared with the app engine so migrations and the API
# always target the same endpoint (see app/core/config.py).
sync_url = (
    f"postgresql+psycopg2://{settings.db_user}:{quote_plus(settings.db_password)}"
    f"@{settings.db_host}:{effective_db_port()}/{settings.db_name}"
)


def run_migrations_offline():
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(sync_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
