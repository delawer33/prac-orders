from src.exceptions.common import NotFoundError


class OrderNotFoundError(NotFoundError):
    public_message = "Order not found"

    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Order not found: {order_id}")
