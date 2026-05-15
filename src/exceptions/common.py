from src.exceptions.base import AppError


class NotFoundError(AppError):
    http_status_code = 404
    log_level = "warning"
    public_message = "Not found"

