class AppError(Exception):
    pass


class IdempotencyKeyAlreadyExistsError(AppError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Idempotency key already exists: {key}")


class OrderNotFoundError(AppError):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Order not found: {order_id}")


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


class UsersServiceUnavailableError(AppError):
    pass


class UsersServiceError(AppError):
    pass


class DownstreamUserNotFoundError(AppError):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")
