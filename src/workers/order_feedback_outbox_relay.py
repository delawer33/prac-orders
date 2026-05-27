import asyncio
import json
import logging

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError

from src.config import Settings
from src.db import SessionFactory
from src.models.order_feedback_outbox import OrderFeedbackCreatedEvent, OrderFeedbackCreatedOutboxModel
from src.repositories.order_feedback_outbox import OrderFeedbackOutboxRepository

logger = logging.getLogger(__name__)


class OrderFeedbackOutboxRelay:
    def __init__(
        self,
        producer: AIOKafkaProducer,
        settings: Settings | None = None,
    ) -> None:
        self._producer = producer
        self._settings = settings or Settings()

    async def run_once(self) -> None:
        await self._reclaim_processing()
        await self._publish_pending_rows()

    async def _reclaim_processing(self) -> None:
        async with SessionFactory() as session:
            await OrderFeedbackOutboxRepository(session).reclaim_processing(
                timeout_seconds=self._settings.kafka_outbox_processing_timeout_seconds
            )
            await session.commit()

    async def _publish_pending_rows(self) -> None:
        rows = await self._claim_pending_batch()
        if not rows:
            return
        await self._relay_rows(rows)

    async def _claim_pending_batch(self) -> list[OrderFeedbackCreatedOutboxModel]:
        async with SessionFactory() as session:
            rows = await OrderFeedbackOutboxRepository(session).claim_pending_batch(
                limit=self._settings.kafka_outbox_batch_size
            )
            await session.commit()
            return rows

    async def _relay_rows(self, rows: list[OrderFeedbackCreatedOutboxModel]) -> None:
        published: list[OrderFeedbackCreatedOutboxModel] = []
        for row in rows:
            try:
                await self._publish_row_to_kafka(row)
                published.append(row)
            except KafkaError:
                logger.exception(
                    "kafka error during relay event_id=%s published_so_far=%d",
                    row.event_id,
                    len(published),
                )
                break
        if published:
            await self._mark_batch_published(published)
            logger.info("outbox relay published %d events", len(published))

    async def _publish_row_to_kafka(self, row: OrderFeedbackCreatedOutboxModel) -> None:
        event = OrderFeedbackCreatedEvent.model_validate(row.payload)
        await self._producer.send_and_wait(
            self._settings.kafka_order_feedback_created_topic,
            value=json.dumps(row.payload).encode("utf-8"),
            key=event.partition_key(),
        )

    async def _mark_batch_published(self, rows: list[OrderFeedbackCreatedOutboxModel]) -> None:
        async with SessionFactory() as session:
            await OrderFeedbackOutboxRepository(session).mark_published(rows)
            await session.commit()


async def run_relay() -> None:
    settings = Settings()
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

    relay = OrderFeedbackOutboxRelay(producer, settings)

    try:
        while True:
            try:
                await relay.run_once()
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
