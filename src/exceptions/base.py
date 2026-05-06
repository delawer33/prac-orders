class AppError(Exception):
    http_status_code: int = 500
    log_level: str = "error"
    public_message: str = "Internal server error"
    log_detail: str | None = None
