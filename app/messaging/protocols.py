from typing import Any, Protocol
from uuid import UUID

from faststream.rabbit import RabbitExchange


class MessagePublisher(Protocol):
    async def publish(
        self,
        message: Any,
        *,
        exchange: RabbitExchange,
        routing_key: str,
        persist: bool,
        message_id: str,
        headers: dict[str, Any] | None = None,
    ) -> Any: ...


class Processor(Protocol):
    async def process(self, payment_id: UUID) -> None: ...
