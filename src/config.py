import os

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
        env_file_encoding='utf-8',
        extra='allow'
    )

    # Database connection
    postgres_url: PostgresDsn = Field(env='postgres_url')

    # Users service integration
    users_service_url: str = Field(env='users_service_url')
    users_service_api_prefix: str = Field(default='/v1/users', env='users_service_api_prefix')
    users_service_http_timeout_seconds: float = Field(default=5.0, env='users_service_http_timeout_seconds')
    
    users_service_retry_attempts: int = Field(default=3, env='users_service_retry_attempts')
    users_service_retry_wait_initial_seconds: float = Field(default=0.5, env='users_service_retry_wait_initial_seconds')
    users_service_retry_wait_exp_base: float = Field(default=2.0, env='users_service_retry_wait_exp_base')
    users_service_retry_wait_max_seconds: float = Field(default=10.0, env='users_service_retry_wait_max_seconds')

    users_service_cb_fail_max: int = Field(default=5, env='users_service_cb_fail_max')
    users_service_cb_timeout_seconds: int = Field(default=30, env='users_service_cb_timeout_seconds')
    users_service_cb_name: str = Field(default='users-service', env='users_service_cb_name')

    # Worker tuning
    saga_worker_poll_interval_seconds: int = Field(default=5, env='saga_worker_poll_interval_seconds')
    saga_worker_batch_size: int = Field(default=20, env='saga_worker_batch_size')
    saga_recovery_grace_seconds: int = Field(default=30, env='saga_recovery_grace_seconds')

    # Kafka
    kafka_bootstrap_servers: str = Field(default='localhost:9092', env='kafka_bootstrap_servers')
    # at least once delivery - consumer должен быть идемпотентным
    kafka_order_feedback_created_topic: str = Field(
        default='orders.order-feedback-created',
        env='kafka_order_feedback_created_topic',
    )
    kafka_outbox_poll_interval_seconds: int = Field(default=5, env='kafka_outbox_poll_interval_seconds')
    kafka_outbox_batch_size: int = Field(default=100, env='kafka_outbox_batch_size')
    kafka_outbox_processing_timeout_seconds: int = Field(default=60, env='kafka_outbox_processing_timeout_seconds')

    # Local app runtime
    app_host: str = Field(default='localhost', env='app_host')
    app_port: int = Field(default=8001, env='app_port')
    app_reload: bool = Field(default=True, env='app_reload')
