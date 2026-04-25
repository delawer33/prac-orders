FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && poetry install --no-root

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

EXPOSE 8001

CMD ["poetry", "run", "uvicorn", "src.application:get_app", "--host", "0.0.0.0", "--port", "8001", "--factory"]
