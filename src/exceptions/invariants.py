from src.exceptions.base import AppError


class InvariantViolationError(AppError):
    http_status_code = 500
    log_level = "error"
    public_message = "Internal state error"
