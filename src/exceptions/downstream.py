from src.exceptions.base import AppError
from src.exceptions.common import NotFoundError


class DownstreamServiceError(AppError):
    http_status_code = 502
    log_level = "error"
    public_message = "Downstream service error"


class UsersServiceUnavailableError(DownstreamServiceError):
    http_status_code = 503
    public_message = "Users service unavailable"


class UsersServiceError(DownstreamServiceError):
    public_message = "Users service error"


class DownstreamUserNotFoundError(NotFoundError):
    public_message = "User not found"

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"User not found: {user_id}")
