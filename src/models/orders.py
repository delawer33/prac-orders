from datetime import datetime
from typing import List
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(sa.Uuid(), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(), default=datetime.utcnow)

    items: Mapped[List["OrderItemModel"]] = relationship(
        "OrderItemModel", back_populates="order", cascade="all, delete-orphan"
    )


class OrderItemModel(Base):
    __tablename__ = "order_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(sa.ForeignKey("orders.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(sa.String(), nullable=False)
    quantity: Mapped[int] = mapped_column(sa.Integer(), nullable=False)
    price: Mapped[float] = mapped_column(sa.Numeric(10, 2), nullable=False)

    order: Mapped["OrderModel"] = relationship("OrderModel", back_populates="items")
