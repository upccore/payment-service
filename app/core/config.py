from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    rabbitmq_url: str
    api_key: str


settings = Settings()
