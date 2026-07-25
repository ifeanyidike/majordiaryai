import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from urllib.parse import quote_plus
from app.core.config import settings
from app.models.base import Base  # noqa: F401 — ensures models are registered

logger = logging.getLogger("app.db")

# Supabase's TRANSACTION pooler (port 6543) hands out a different server
# connection per transaction, which breaks asyncpg's prepared statements
# (InvalidSQLStatementNameError → intermittent 500s). A long-lived API server
# should use the SESSION pooler (5432) or a direct connection, both of which
# keep a stable backend connection and support prepared statements. Remap the
# transaction-pooler port to the session pooler automatically.
_port = settings.db_port
if _port == 6543:
    logger.warning(
        "DB_PORT 6543 is the transaction pooler (no prepared-statement support); "
        "connecting via the session pooler on 5432 instead."
    )
    _port = 5432

# URL-encode password to safely handle special characters like @
db_url = (
    f"postgresql+asyncpg://{settings.db_user}:{quote_plus(settings.db_password)}"
    f"@{settings.db_host}:{_port}/{settings.db_name}"
)

engine = create_async_engine(db_url, echo=False, pool_size=5, max_overflow=10)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session
