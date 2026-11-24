"""Pydantic schemas for authentication, inventory, sales, cash register, and reports."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=4, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ProductCreate(BaseModel):
    sku: str = Field(min_length=2, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(default="General", min_length=2, max_length=80)
    unit_price: Decimal = Field(gt=Decimal("0"))
    stock: int = Field(ge=0, default=0)
    min_stock: int = Field(ge=0, default=5)
    expires_at: date | None = None


class RestockRequest(BaseModel):
    quantity: int = Field(gt=0, description="Unidades a sumar al stock actual.")


class ProductResponse(BaseModel):
    id: int
    sku: str
    name: str
    category: str
    unit_price: Decimal
    stock: int
    min_stock: int
    expires_at: date | None
    is_low_stock: bool
    expiry_status: Literal["ok", "expiring_soon", "expired"]


class SaleItemCreate(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class SaleCreate(BaseModel):
    customer_name: str = Field(default="Cliente Varios", min_length=2, max_length=120)
    payment_method: Literal["cash", "card", "yape_plin"] = "cash"
    items: list[SaleItemCreate] = Field(min_length=1)


class SaleItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class SaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: str
    customer_name: str
    payment_method: str
    subtotal: Decimal
    igv: Decimal
    total: Decimal
    created_at: datetime
    items: list[SaleItemResponse]


class CashOpenRequest(BaseModel):
    opening_amount: Decimal = Field(ge=Decimal("0"))


class CashCloseRequest(BaseModel):
    closing_amount: Decimal = Field(ge=Decimal("0"))


class CashSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    opened_at: datetime
    closed_at: datetime | None
    opening_amount: Decimal
    closing_amount: Decimal | None
    expected_amount: Decimal | None
    difference: Decimal | None
    status: str


class AlertsResponse(BaseModel):
    low_stock: list[ProductResponse]
    expiring_or_expired: list[ProductResponse]


class DashboardSummary(BaseModel):
    total_products: int
    low_stock_count: int
    expiring_count: int
    today_sales_count: int
    today_revenue: Decimal
    total_revenue: Decimal
    has_open_cash_session: bool
