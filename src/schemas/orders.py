from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, model_validator


class OrderItemCreate(BaseModel):
    product_name: str
    quantity: int
    price: float


class OrderCreate(BaseModel):
    user_id: UUID | None = None
    email: EmailStr | None = None
    title: str
    items: List[OrderItemCreate]

    @model_validator(mode="after")
    def validate_user_selector(self) -> "OrderCreate":
        if (self.user_id is None) == (self.email is None):
            raise ValueError("Exactly one of user_id or email must be provided")
        return self


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
    items: List[OrderItemRead]


class UserRead(BaseModel):
    id: UUID
    username: str | None
    email: str
    first_name: str | None
    last_name: str | None
    is_active: bool
    created_at: datetime


class UserResolveResponse(BaseModel):
    user: UserRead
    created: bool


class OrderUser(BaseModel):
    order: OrderRead
    user: UserRead
