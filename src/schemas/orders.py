from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OrderItemCreate(BaseModel):
    product_name: str
    quantity: int
    price: float


class OrderCreate(BaseModel):
    user_id: UUID
    title: str
    items: list[OrderItemCreate]


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_name: str
    quantity: int
    price: float


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    title: str
    created_at: datetime
    items: list[OrderItemRead]


class UserRead(BaseModel):
    id: UUID
    username: str


class OrderUser(BaseModel):
    order: OrderRead
    user: UserRead
