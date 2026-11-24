"""Idempotent seed data (demo users and sample products for quick testing)."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from stockflow_pos.core.security import hash_password
from stockflow_pos.models.entities import Product, User


def seed_initial_data(db: Session) -> None:
    """Create default demo accounts and sample inventory if database is empty."""
    has_users = db.execute(select(User.id).limit(1)).scalar_one_or_none()
    if has_users is None:
        db.add_all(
            [
                User(
                    username="admin",
                    full_name="Administrador General",
                    role="admin",
                    password_hash=hash_password("admin123"),
                ),
                User(
                    username="cajero",
                    full_name="Cajero Turno Mañana",
                    role="cashier",
                    password_hash=hash_password("cajero123"),
                ),
            ]
        )

    has_products = db.execute(select(Product.id).limit(1)).scalar_one_or_none()
    if has_products is None:
        today = date.today()
        db.add_all(
            [
                Product(
                    sku="BEB-001",
                    name="Inca Kola 500ml",
                    category="Bebidas",
                    unit_price=Decimal("3.50"),
                    stock=40,
                    min_stock=10,
                    expires_at=today + timedelta(days=120),
                ),
                Product(
                    sku="BEB-002",
                    name="Agua San Luis 625ml",
                    category="Bebidas",
                    unit_price=Decimal("2.00"),
                    stock=8,
                    min_stock=12,
                    expires_at=today + timedelta(days=90),
                ),
                Product(
                    sku="LAC-001",
                    name="Leche Gloria Azul 400g",
                    category="Lácteos",
                    unit_price=Decimal("4.80"),
                    stock=25,
                    min_stock=8,
                    expires_at=today + timedelta(days=14),
                ),
                Product(
                    sku="SNK-001",
                    name="Galletas Soda Field Pack",
                    category="Snacks",
                    unit_price=Decimal("5.50"),
                    stock=4,
                    min_stock=6,
                    expires_at=today + timedelta(days=45),
                ),
                Product(
                    sku="ABR-001",
                    name="Arroz Costeño Extra 1kg",
                    category="Abarrotes",
                    unit_price=Decimal("5.20"),
                    stock=30,
                    min_stock=10,
                    expires_at=today + timedelta(days=180),
                ),
            ]
        )

    db.commit()
