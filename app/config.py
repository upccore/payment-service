from pydantic_settings import BaseSettings, SettingsConfigDict

PAYMENTS_QUEUE = "payments.new"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    rabbitmq_url: str
    api_key: str


settings = Settings()
