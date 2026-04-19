# Orders Service

## Запуск

**1. Поднять БД**

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
