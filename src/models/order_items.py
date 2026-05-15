from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(sa.ForeignKey("orders.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(sa.String(), nullable=False)
    quantity: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    price: Mapped[float] = mapped_column(sa.Numeric(10, 2), nullable=False)

    order: Mapped["OrderModel"] = relationship("OrderModel", back_populates="items")
