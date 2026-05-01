from src.exceptions.base import AppError


class IdempotencyKeyAlreadyExistsError(AppError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Idempotency key already exists: {key}")


class IdempotencyConflictError(AppError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Idempotency key reused with different payload: {key}")


class IdempotencyInProgressError(AppError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Order creation in progress for idempotency key: {key}")


class IdempotencyFailedError(AppError):
    def __init__(self, key: str, reason: str | None = None) -> None:
        self.key = key
        self.reason = reason
        details = f": {reason}" if reason else ""
        super().__init__(f"Order creation failed for idempotency key: {key}{details}")
