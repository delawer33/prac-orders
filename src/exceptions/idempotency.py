from src.exceptions.base import AppError


class IdempotencyError(AppError):
    http_status_code = 409
    log_level = "warning"
    public_message = "Idempotency conflict"


class IdempotencyKeyAlreadyExistsError(AppError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Idempotency key already exists: {key}")


class IdempotencyConflictError(IdempotencyError):
    public_message = "Idempotency key reused with different payload"

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Idempotency key reused with different payload: {key}")


class IdempotencyInProgressError(IdempotencyError):
    public_message = "Order creation already in progress for this key"

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Order creation in progress for idempotency key: {key}")


class IdempotencyFailedError(IdempotencyError):
    public_message = "Order creation failed for this key"

    def __init__(self, key: str, reason: str | None = None) -> None:
        self.key = key
        self.reason = reason
        self.public_message = reason or "Order creation failed for this key"
        details = f": {reason}" if reason else ""
        super().__init__(f"Order creation failed for idempotency key: {key}{details}")
