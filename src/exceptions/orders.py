from src.exceptions.base import AppError


class OrderNotFoundError(AppError):
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Order not found: {order_id}")
