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
    farm_timezone: str = "America/Toronto"
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
