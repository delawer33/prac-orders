import asyncio
import json
import logging

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config import Settings
from src.db import SessionFactory
from src.repositories.outbox import OutboxRepository

logger = logging.getLogger(__name__)
settings = Settings()


async def _publish_batch(producer: AIOKafkaProducer) -> None:
    async with SessionFactory() as session:
        repo = OutboxRepository(session)
        rows = await repo.get_pending_batch(limit=settings.kafka_outbox_batch_size)
        if not rows:
            await session.commit()
            return

        for row in rows:
            partition_key = row.payload.get("data", {}).get("user_id", "").encode("utf-8")
            value = json.dumps(row.payload).encode("utf-8")
            await producer.send(
                settings.kafka_order_created_topic,
                value=value,
                key=partition_key,
            )

        await producer.flush()
        await repo.mark_published(rows)
        await session.commit()
        logger.info("outbox relay published %d events", len(rows))


async def run_relay() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        acks="all",
        enable_idempotence=True,
        value_serializer=None,
        key_serializer=None,
    )
    await producer.start()
    logger.info("outbox relay started")

    try:
        while True:
            try:
                await _publish_batch(producer)
            except KafkaError:
                logger.exception("kafka error during relay — will retry next poll")
            except Exception:
                logger.exception("unexpected relay error — will retry next poll")
            await asyncio.sleep(settings.kafka_outbox_poll_interval_seconds)
    finally:
        await producer.stop()
        logger.info("outbox relay stopped")


if __name__ == "__main__":
    asyncio.run(run_relay())
