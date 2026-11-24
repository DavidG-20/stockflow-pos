"""REST API endpoints for StockFlow POS with role-based access control."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from stockflow_pos.core.database import get_db
from stockflow_pos.core.security import (
    create_access_token,
    enforce_login_rate_limit,
    get_current_user,
    require_admin,
    verify_password,
)
from stockflow_pos.models.entities import User
from stockflow_pos.schemas.pos import (
    AlertsResponse,
    CashCloseRequest,
    CashOpenRequest,
    CashSessionResponse,
    DashboardSummary,
    LoginRequest,
    ProductCreate,
    ProductResponse,
    RestockRequest,
    SaleCreate,
    SaleResponse,
    TokenResponse,
    UserResponse,
)
from stockflow_pos.services.pos_service import (
    CashSessionConflictError,
    CashSessionNotFoundError,
    DuplicateSKUError,
    InsufficientStockError,
    ProductNotFoundError,
    close_cash_session,
    create_product,
    create_sale,
    export_sales_csv,
    get_alerts,
    get_dashboard_summary,
    get_open_cash_session,
    list_products,
    list_sales,
    open_cash_session,
    restock_product,
)

router = APIRouter(prefix="/api/v1")


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
    tags=["auth"],
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Autentica al usuario y devuelve un token JWT Bearer."""
    user = db.execute(
        select(User).where(User.username == payload.username.strip())
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos.",
        )

    token = create_access_token(user)
    return TokenResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/auth/me", response_model=UserResponse, tags=["auth"])
def read_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Devuelve el perfil del usuario autenticado."""
    return UserResponse.model_validate(current_user)


@router.get("/dashboard", response_model=DashboardSummary, tags=["dashboard"])
def read_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummary:
    """Devuelve indicadores clave del negocio (KPIs)."""
    return get_dashboard_summary(db, current_user)


@router.get("/products", response_model=list[ProductResponse], tags=["inventory"])
def read_products(
    search: str | None = None,
    low_stock_only: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[ProductResponse]:
    """Lista los productos del inventario con filtros opcionales."""
    return list_products(db, search=search, low_stock_only=low_stock_only)


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["inventory"],
)
def add_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ProductResponse:
    """Crea un producto nuevo en el catálogo (solo administradores)."""
    try:
        return create_product(db, payload)
    except DuplicateSKUError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch(
    "/products/{product_id}/restock",
    response_model=ProductResponse,
    tags=["inventory"],
)
def add_stock(
    product_id: int,
    payload: RestockRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> ProductResponse:
    """Suma stock a un producto existente (solo administradores)."""
    try:
        return restock_product(db, product_id, payload.quantity)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/alerts", response_model=AlertsResponse, tags=["inventory"])
def read_alerts(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> AlertsResponse:
    """Lista alertas de stock mínimo y productos próximos a vencer o vencidos."""
    return get_alerts(db)


@router.get("/cash/current", response_model=CashSessionResponse | None, tags=["cash"])
def read_current_cash(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CashSessionResponse | None:
    """Devuelve la sesión de caja abierta del usuario actual (o null)."""
    session = get_open_cash_session(db, current_user)
    return CashSessionResponse.model_validate(session) if session else None


@router.post(
    "/cash/open",
    response_model=CashSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["cash"],
)
def open_cash(
    payload: CashOpenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CashSessionResponse:
    """Abre un turno de caja con un monto inicial."""
    try:
        session = open_cash_session(db, current_user, payload.opening_amount)
    except CashSessionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CashSessionResponse.model_validate(session)


@router.post("/cash/close", response_model=CashSessionResponse, tags=["cash"])
def close_cash(
    payload: CashCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CashSessionResponse:
    """Cierra el turno de caja abierto y calcula el cuadre (sobrante/faltante)."""
    try:
        session = close_cash_session(db, current_user, payload.closing_amount)
    except CashSessionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return CashSessionResponse.model_validate(session)


@router.get("/sales", response_model=list[SaleResponse], tags=["sales"])
def read_sales(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[SaleResponse]:
    """Lista el historial reciente de ventas."""
    return [SaleResponse.model_validate(sale) for sale in list_sales(db)]


@router.post(
    "/sales",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["sales"],
)
def register_sale(
    payload: SaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SaleResponse:
    """Registra una venta POS descontando stock de forma atómica y generando comprobante."""
    try:
        sale = create_sale(db, current_user, payload)
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InsufficientStockError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return SaleResponse.model_validate(sale)


@router.get("/reports/sales.csv", tags=["reports"])
def download_sales_csv(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    """Descarga el reporte de ventas en formato CSV compatible con Excel (solo admin)."""
    csv_content = export_sales_csv(db)
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reporte_ventas.csv"'},
    )
