"""End-to-end integration tests for StockFlow POS."""

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient


def auth_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_health_and_frontend_served(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    home = client.get("/")
    assert home.status_code == 200
    assert "StockFlow POS" in home.text


def test_auth_login_and_role_based_access(client: TestClient) -> None:
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401

    cashier_headers = auth_headers(client, "cajero", "cajero123")
    forbidden_create = client.post(
        "/api/v1/products",
        headers=cashier_headers,
        json={
            "sku": "TST-001",
            "name": "Producto Prohibido",
            "category": "Test",
            "unit_price": "10.00",
            "stock": 5,
            "min_stock": 2,
        },
    )
    assert forbidden_create.status_code == 403

    forbidden_csv = client.get("/api/v1/reports/sales.csv", headers=cashier_headers)
    assert forbidden_csv.status_code == 403


def test_inventory_create_duplicate_restock_and_alerts(client: TestClient) -> None:
    admin_headers = auth_headers(client, "admin", "admin123")

    created = client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "sku": "BOT-001",
            "name": "Paracetamol 500mg",
            "category": "Farmacia",
            "unit_price": "6.50",
            "stock": 2,
            "min_stock": 5,
            "expires_at": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    assert created.status_code == 201
    product = created.json()
    assert product["is_low_stock"] is True
    assert product["expiry_status"] == "expiring_soon"

    dup = client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "sku": "BOT-001",
            "name": "Duplicado",
            "category": "Farmacia",
            "unit_price": "6.50",
            "stock": 1,
            "min_stock": 1,
        },
    )
    assert dup.status_code == 409

    restocked = client.patch(
        f"/api/v1/products/{product['id']}/restock",
        headers=admin_headers,
        json={"quantity": 10},
    )
    assert restocked.status_code == 200
    assert restocked.json()["stock"] == 12
    assert restocked.json()["is_low_stock"] is False

    alerts = client.get("/api/v1/alerts", headers=admin_headers).json()
    assert any(p["sku"] == "BOT-001" for p in alerts["expiring_or_expired"])


def test_atomic_sale_igv_calculation_and_stock_protection(client: TestClient) -> None:
    cashier_headers = auth_headers(client, "cajero", "cajero123")
    products = client.get("/api/v1/products", headers=cashier_headers).json()
    p1, p2 = products[0], products[1]
    initial_stock_p1 = p1["stock"]

    # Attempt an impossible sale (valid p1 + excessive p2): must reject atomically
    failed_sale = client.post(
        "/api/v1/sales",
        headers=cashier_headers,
        json={
            "customer_name": "María López",
            "payment_method": "yape_plin",
            "items": [
                {"product_id": p1["id"], "quantity": 1},
                {"product_id": p2["id"], "quantity": p2["stock"] + 50},
            ],
        },
    )
    assert failed_sale.status_code == 409

    # Verify p1 stock was NOT decremented after failed transaction
    refreshed_p1 = next(
        p
        for p in client.get("/api/v1/products", headers=cashier_headers).json()
        if p["id"] == p1["id"]
    )
    assert refreshed_p1["stock"] == initial_stock_p1

    # Valid sale
    ok_sale = client.post(
        "/api/v1/sales",
        headers=cashier_headers,
        json={
            "customer_name": "Carlos Pérez",
            "payment_method": "cash",
            "items": [{"product_id": p1["id"], "quantity": 2}],
        },
    )
    assert ok_sale.status_code == 201
    sale = ok_sale.json()
    assert sale["receipt_number"] == "B001-000001"
    expected_total = Decimal(p1["unit_price"]) * 2
    assert Decimal(sale["total"]) == expected_total
    assert Decimal(sale["subtotal"]) + Decimal(sale["igv"]) == expected_total


def test_cash_session_lifecycle_and_csv_report(client: TestClient) -> None:
    admin_headers = auth_headers(client, "admin", "admin123")

    opened = client.post(
        "/api/v1/cash/open",
        headers=admin_headers,
        json={"opening_amount": "100.00"},
    )
    assert opened.status_code == 201

    second_open = client.post(
        "/api/v1/cash/open",
        headers=admin_headers,
        json={"opening_amount": "50.00"},
    )
    assert second_open.status_code == 409

    products = client.get("/api/v1/products", headers=admin_headers).json()
    sale_resp = client.post(
        "/api/v1/sales",
        headers=admin_headers,
        json={
            "customer_name": "Ana Torres",
            "payment_method": "cash",
            "items": [{"product_id": products[0]["id"], "quantity": 2}],
        },
    )
    assert sale_resp.status_code == 201
    sale_total = Decimal(sale_resp.json()["total"])

    expected_cash = Decimal("100.00") + sale_total
    closed = client.post(
        "/api/v1/cash/close",
        headers=admin_headers,
        json={"closing_amount": str(expected_cash + Decimal("5.00"))},
    )
    assert closed.status_code == 200
    assert Decimal(closed.json()["expected_amount"]) == expected_cash
    assert Decimal(closed.json()["difference"]) == Decimal("5.00")

    csv_resp = client.get("/api/v1/reports/sales.csv", headers=admin_headers)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "B001-000001" in csv_resp.text
