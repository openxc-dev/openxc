from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "openxc"
    postgres_password: str = "openxc"
    postgres_db: str = "openxc"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    valkey_host: str = "valkey"
    valkey_port: int = 6379

    cors_origins: str = "*"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
