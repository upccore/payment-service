from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    rabbitmq_url: str
    api_key: str
    db_pool_size: int = 10
    db_max_overflow: int = 5
    consumer_prefetch: int = 10
    gateway_timeout: float = 30
    webhook_timeout: float = 10
    log_level: str = "INFO"

    @model_validator(mode="after")
    def check_pool_fits_prefetch(self) -> Self:
        """Каждое сообщение в обработке держит соединение с базой, пока ждёт шлюз."""
        if self.consumer_prefetch > self.db_pool_size:
            raise ValueError("consumer_prefetch must not exceed db_pool_size")
        return self


settings = Settings()
