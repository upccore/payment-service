from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def test_unpublished_outbox_index_is_used(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        definition = await session.scalar(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE indexname = 'ix_outbox_unpublished'"
            )
        )
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            await session.scalars(
                text(
                    "EXPLAIN SELECT * FROM outbox WHERE published_at IS NULL "
                    "ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED"
                )
            )
        )

    assert definition is not None
    assert "WHERE (published_at IS NULL)" in definition
    assert "ix_outbox_unpublished" in plan
