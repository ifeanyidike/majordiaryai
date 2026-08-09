from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    # IANA zone, NOT a fixed offset: "America/Toronto" is Eastern time WITH
    # daylight saving, whereas a literal "EST" would be an hour out all summer.
    # Every report asks "what day is it locally", so this must track DST.
    farm_timezone: str = "America/Toronto"
    # How often the lifecycle sweep runs (dry-off, fresh→open, calf→heifer …).
    # 6h keeps a day-223 dry-off notice timely without hammering the database;
    # 0 disables the loop (used by tests, which drive the sweep directly).
    sweep_interval_seconds: int = 6 * 60 * 60
    # Comma-separated list of allowed CORS origins (Expo dev defaults).
    cors_origins: str = "http://localhost:8081,http://localhost:19006"

    # Email (SendGrid). Leave SENDGRID_API_KEY empty to disable sending — the
    # email service then safely no-ops and just logs. Team fills the key in.
    sendgrid_api_key: str = ""
    email_from: str = "no-reply@majordairy.ai"
    email_from_name: str = "Major Dairy AI"

    class Config:
        env_file = ".env"


settings = Settings()

# Supabase's TRANSACTION pooler (6543) hands out a different server connection
# per transaction, which breaks prepared statements. The SESSION pooler (5432)
# keeps a stable backend connection. Both the app engine and Alembic must agree
# on this — when only the app remapped, migrations silently ran against a
# different endpoint than the API.
TRANSACTION_POOLER_PORT = 6543
SESSION_POOLER_PORT = 5432


def effective_db_port(port: Optional[int] = None) -> int:
    """The port to actually connect on, remapping the transaction pooler."""
    port = settings.db_port if port is None else port
    return SESSION_POOLER_PORT if port == TRANSACTION_POOLER_PORT else port
