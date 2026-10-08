import pytest
from pydantic import ValidationError

from app.core.config import Settings

REQUIRED = {"database_url": "db", "rabbitmq_url": "amqp", "api_key": "key"}


def test_prefetch_within_pool_is_accepted() -> None:
    settings = Settings(**REQUIRED, db_pool_size=10, consumer_prefetch=10)

    assert settings.consumer_prefetch == 10


def test_prefetch_above_pool_is_rejected() -> None:
    with pytest.raises(ValidationError, match="consumer_prefetch"):
        Settings(**REQUIRED, db_pool_size=5, consumer_prefetch=10)
