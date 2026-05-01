from src.exceptions.base import AppError


class SagaInvariantError(AppError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
