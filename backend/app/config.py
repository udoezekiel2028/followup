from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "SmartFollow AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    FRONTEND_URL: str = "http://localhost:3000"
    SECRET_KEY: str = "smartfollow-ai-secret-key-at-least-32-chars-long-2026"
    TOKEN_ENCRYPTION_KEY: Optional[str] = None

    # Supabase / Database
    SUPABASE_URL: Optional[str] = None
    SUPABASE_SERVICE_KEY: Optional[str] = None
    DATABASE_URL: Optional[str] = None # sqlite:///./cold_email.db fallback

    # OpenAI API
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_DEFAULT_MODEL: str = "gpt-4o-mini"

    # Google OAuth 2.0
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"
    GOOGLE_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid"
    ]
    GMAIL_LABEL_NAME: str = "AUTO_FOLLOWUP"

    # Automation Engine Defaults (Production Live Mode)
    DEFAULT_FOLLOW_UP_DELAY_HOURS: int = 72 # 3 days default
    DEFAULT_TEST_MODE: bool = False # Production Live Mode (sends real emails)
    DEFAULT_AUTO_SEND: bool = True # Auto-send enabled for real-time dispatch
    DEFAULT_MAX_FOLLOWUPS: int = 1
    SCHEDULER_INTERVAL_MINUTES: int = 60 # Hourly check

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
