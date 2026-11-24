"""Core business logic for inventory, atomic POS sales, cash register, and reports."""

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import io
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from stockflow_pos.core.config import settings
from stockflow_pos.models.entities import CashSession, Product, Sale, SaleItem, User
from stockflow_pos.schemas.pos import (
    AlertsResponse,
    DashboardSummary,
    ProductCreate,
    ProductResponse,
    SaleCreate,
)

TWO_DECIMALS = Decimal("0.01")


class DuplicateSKUError(Exception):
    """Raised when creating a product with an existing SKU."""


class ProductNotFoundError(Exception):
    """Raised when a requested product does not exist."""


class InsufficientStockError(Exception):
    """Raised when a sale requests more units than available in stock."""


class CashSessionConflictError(Exception):
    """Raised when opening a second cash session while one is already open."""


class CashSessionNotFoundError(Exception):
    """Raised when trying to close a cash session that does not exist."""


def _money(value: Decimal) -> Decimal:
    return value.quantize(TWO_DECIMALS, rounding=ROUND_HALF_UP)


def _compute_expiry_status(expires_at: date | None) -> Literal["ok", "expiring_soon", "expired"]:
    if expires_at is None:
        return "ok"
    today = date.today()
    if expires_at < today:
        return "expired"
    if expires_at <= today + timedelta(days=settings.expiry_alert_days):
        return "expiring_soon"
    return "ok"


def to_product_response(product: Product) -> ProductResponse:
    """Convert an ORM Product into its API response with alert flags."""
    return ProductResponse(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        unit_price=_money(Decimal(product.unit_price)),
        stock=product.stock,
        min_stock=product.min_stock,
        expires_at=product.expires_at,
        is_low_stock=product.stock <= product.min_stock,
        expiry_status=_compute_expiry_status(product.expires_at),
    )


def list_products(
    db: Session,
    search: str | None = None,
    low_stock_only: bool = False,
) -> list[ProductResponse]:
    """List active products with optional name/SKU filter and low-stock filter."""
    stmt = select(Product).where(Product.is_active.is_(True)).order_by(Product.name.asc())
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where((Product.name.ilike(term)) | (Product.sku.ilike(term)))
    if low_stock_only:
        stmt = stmt.where(Product.stock <= Product.min_stock)

    products = db.execute(stmt).scalars().all()
    return [to_product_response(product) for product in products]


def create_product(db: Session, payload: ProductCreate) -> ProductResponse:
    """Create a new product ensuring SKU uniqueness."""
    existing = db.execute(
        select(Product.id).where(Product.sku == payload.sku.upper())
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateSKUError(f"El SKU '{payload.sku.upper()}' ya existe.")

    product = Product(
        sku=payload.sku.upper(),
        name=payload.name.strip(),
        category=payload.category.strip(),
        unit_price=_money(payload.unit_price),
        stock=payload.stock,
        min_stock=payload.min_stock,
        expires_at=payload.expires_at,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return to_product_response(product)


def restock_product(db: Session, product_id: int, quantity: int) -> ProductResponse:
    """Increase stock for an existing product."""
    product = db.execute(
        select(Product).where(Product.id == product_id, Product.is_active.is_(True))
    ).scalar_one_or_none()
    if product is None:
        raise ProductNotFoundError(f"Producto con ID {product_id} no encontrado.")

    product.stock += quantity
    db.commit()
    db.refresh(product)
    return to_product_response(product)


def get_alerts(db: Session) -> AlertsResponse:
    """Return products with low stock or upcoming/past expiration dates."""
    all_products = list_products(db)
    low_stock = [p for p in all_products if p.is_low_stock]
    expiring_or_expired = [p for p in all_products if p.expiry_status != "ok"]
    return AlertsResponse(low_stock=low_stock, expiring_or_expired=expiring_or_expired)


def get_open_cash_session(db: Session, user: User) -> CashSession | None:
    """Return the active open cash register session for the given user, if any."""
    stmt = (
        select(CashSession)
        .where(CashSession.user_id == user.id, CashSession.status == "open")
        .order_by(CashSession.opened_at.desc())
    )
    return db.execute(stmt).scalar_one_or_none()


def open_cash_session(db: Session, user: User, opening_amount: Decimal) -> CashSession:
    """Open a new cash register shift if the user does not already have one open."""
    if get_open_cash_session(db, user) is not None:
        raise CashSessionConflictError("Ya tienes una sesión de caja abierta.")

    session = CashSession(
        user_id=user.id,
        opening_amount=_money(opening_amount),
        status="open",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def close_cash_session(db: Session, user: User, closing_amount: Decimal) -> CashSession:
    """Close the open cash session and calculate expected balance and difference."""
    session = get_open_cash_session(db, user)
    if session is None:
        raise CashSessionNotFoundError("No tienes ninguna sesión de caja abierta.")

    cash_sales_total = db.execute(
        select(func.coalesce(func.sum(Sale.total), 0)).where(
            Sale.cash_session_id == session.id,
            Sale.payment_method == "cash",
        )
    ).scalar_one()

    expected = _money(Decimal(session.opening_amount) + Decimal(cash_sales_total))
    counted = _money(closing_amount)

    session.closing_amount = counted
    session.expected_amount = expected
    session.difference = _money(counted - expected)
    session.closed_at = datetime.now(timezone.utc)
    session.status = "closed"

    db.commit()
    db.refresh(session)
    return session


def _next_receipt_number(db: Session) -> str:
    last_id = db.execute(select(func.coalesce(func.max(Sale.id), 0))).scalar_one()
    return f"B001-{int(last_id) + 1:06d}"


def create_sale(db: Session, user: User, payload: SaleCreate) -> Sale:
    """Validate stock atomically for all items, compute IGV, and persist the sale."""
    # Aggregate quantities in case the same product_id appears twice in payload
    requested_by_product: dict[int, int] = {}
    for item in payload.items:
        requested_by_product[item.product_id] = (
            requested_by_product.get(item.product_id, 0) + item.quantity
        )

    products = (
        db.execute(
            select(Product).where(
                Product.id.in_(list(requested_by_product.keys())),
                Product.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    products_by_id = {product.id: product for product in products}

    for product_id, qty in requested_by_product.items():
        product = products_by_id.get(product_id)
        if product is None:
            raise ProductNotFoundError(f"Producto con ID {product_id} no encontrado.")
        if product.stock < qty:
            raise InsufficientStockError(
                f"Stock insuficiente para '{product.name}' "
                f"(disponible: {product.stock}, solicitado: {qty})."
            )

    total = Decimal("0.00")
    sale_items: list[SaleItem] = []

    for product_id, qty in requested_by_product.items():
        product = products_by_id[product_id]
        unit_price = _money(Decimal(product.unit_price))
        line_total = _money(unit_price * qty)
        total += line_total
        product.stock -= qty
        sale_items.append(
            SaleItem(
                product_id=product.id,
                product_name=product.name,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    total = _money(total)
    subtotal = _money(total / (Decimal("1") + settings.igv_rate))
    igv = _money(total - subtotal)

    open_session = get_open_cash_session(db, user)
    sale = Sale(
        receipt_number=_next_receipt_number(db),
        user_id=user.id,
        cash_session_id=open_session.id if open_session else None,
        customer_name=payload.customer_name.strip(),
        payment_method=payload.payment_method,
        subtotal=subtotal,
        igv=igv,
        total=total,
        items=sale_items,
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale


def list_sales(db: Session, limit: int = 50) -> list[Sale]:
    """Return most recent sales with their line items."""
    stmt = select(Sale).order_by(Sale.created_at.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def get_dashboard_summary(db: Session, user: User) -> DashboardSummary:
    """Compute KPIs for the main dashboard."""
    alerts = get_alerts(db)
    total_products = db.execute(
        select(func.count(Product.id)).where(Product.is_active.is_(True))
    ).scalar_one()

    start_of_today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_count, today_sum = db.execute(
        select(
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.total), 0),
        ).where(Sale.created_at >= start_of_today)
    ).one()

    total_revenue = db.execute(select(func.coalesce(func.sum(Sale.total), 0))).scalar_one()

    return DashboardSummary(
        total_products=int(total_products),
        low_stock_count=len(alerts.low_stock),
        expiring_count=len(alerts.expiring_or_expired),
        today_sales_count=int(today_count),
        today_revenue=_money(Decimal(today_sum)),
        total_revenue=_money(Decimal(total_revenue)),
        has_open_cash_session=get_open_cash_session(db, user) is not None,
    )


def _sanitize_csv_cell(value: str) -> str:
    """Prevent spreadsheet formula injection when exporting user text to CSV."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return value


def export_sales_csv(db: Session) -> str:
    """Generate a UTF-8 CSV report of all sales ready to open in Excel."""
    sales = list_sales(db, limit=1000)
    buffer = io.StringIO()
    buffer.write("\ufeff")  # UTF-8 BOM for clean Excel accents
    writer = csv.writer(buffer)
    writer.writerow(
        ["Comprobante", "Fecha UTC", "Cliente", "Método de Pago", "Subtotal (S/)", "IGV (S/)", "Total (S/)"]
    )
    for sale in sales:
        writer.writerow(
            [
                sale.receipt_number,
                sale.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                _sanitize_csv_cell(sale.customer_name),
                sale.payment_method,
                f"{Decimal(sale.subtotal):.2f}",
                f"{Decimal(sale.igv):.2f}",
                f"{Decimal(sale.total):.2f}",
            ]
        )
    return buffer.getvalue()
