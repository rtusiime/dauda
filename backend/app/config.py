from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./channel_manager.db"
    background_poll_interval_seconds: int = 300
    default_admin_email: str = "admin@example.com"
    default_admin_password: str = "ChangeMe123!"

    class Config:
        env_prefix = "CHANNEL_MANAGER_"
        env_file = ".env"


settings = Settings()
