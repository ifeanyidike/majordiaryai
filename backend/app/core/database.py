import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from urllib.parse import quote_plus
from app.core.config import effective_db_port, settings
from app.models.base import Base  # noqa: F401 — ensures models are registered

logger = logging.getLogger("app.db")

# Shared with Alembic (see config.effective_db_port): the transaction pooler
# breaks asyncpg's prepared statements, so 6543 is remapped to the session
# pooler on 5432.
_port = effective_db_port()
if _port != settings.db_port:
    logger.warning(
        "DB_PORT %s is the transaction pooler (no prepared-statement support); "
        "connecting via the session pooler on %s instead.", settings.db_port, _port
    )

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
