from src.exceptions.base import AppError


class UsersServiceUnavailableError(AppError):
    pass


class UsersServiceError(AppError):
    pass


class DownstreamUserNotFoundError(AppError):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")
