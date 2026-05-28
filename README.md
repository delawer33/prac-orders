# Orders Service

## Запуск

**1. Поднять инфраструктуру (Postgres, Kafka)**

```bash
docker compose up -d
```

**2. Применить миграции**

```bash
poetry run alembic upgrade head
```

**3. Запустить сервис**

```bash
poetry run python -m src.main
```

Документация доступна по адресу: http://localhost:8001/docs

**4. Запустить воркеры**

Компенсационный воркер (saga recovery):
```bash
poetry run python -m src.workers.compensation_worker
```

Outbox relay (публикация событий в Kafka):
```bash
poetry run python -m src.workers.order_feedback_outbox_relay
```

В Docker все воркеры поднимаются автоматически через `docker compose up`.

## Kafka события

| Топик | Событие | Ключ партиции |
|---|---|---|
| `orders.order-feedback-created` | `OrderFeedbackCreated` | `user_id` |

Доставка **at-least-once** — консюмеры должны быть идемпотентными. Для дедупликации использовать `event_id` из payload.
