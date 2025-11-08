from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./channel_manager.db"

    class Config:
        env_prefix = "CHANNEL_MANAGER_"
        env_file = ".env"


settings = Settings()
