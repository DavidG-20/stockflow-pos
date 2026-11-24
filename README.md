# StockFlow POS — Sistema de Inventario y Punto de Venta

Sistema **Full-Stack** de gestión de inventario, punto de venta (POS), control de caja y reportes para pequeños negocios (bodegas, boticas o minimarkets), construido con **FastAPI**, **SQLAlchemy 2.x**, **JWT**, interfaz web moderna y **Docker Compose + PostgreSQL**.

## Características principales

- **Autenticación y roles (JWT)**:
  - Contraseñas protegidas con `PBKDF2-HMAC-SHA256` + salt aleatorio y sesiones mediante tokens **JWT Bearer**.
  - **Administrador (`admin`)**: gestiona catálogo, reposiciones de stock, reportes CSV y operación de caja/ventas.
  - **Cajero (`cashier`)**: consulta catálogo, abre/cierra su turno de caja y registra ventas.
- **Inventario con alertas automáticas**:
  - Control de SKU único, precio en Soles (`S/`), stock mínimo y fecha de vencimiento.
  - Alertas de **stock bajo** (`stock <= min_stock`) y productos **por vencer en ≤ 30 días o vencidos**.
- **Punto de Venta (POS) atómico**:
  - Valida el stock de todos los ítems antes de descontar en una sola transacción (nunca permite stock negativo; rechaza con `409 Conflict`).
  - Soporta pagos en **Efectivo**, **Yape / Plin** y **Tarjeta**.
  - Genera comprobante simulado (`B001-000001`) con desglose exacto de **Subtotal**, **IGV (18%)** y **Total**, listo para imprimir.
- **Control y cuadre de caja**:
  - Apertura y cierre de turno por usuario, calculando automáticamente el efectivo esperado y la diferencia (sobrante/faltante).
- **Reportes descargables**:
  - Exportación de ventas a **CSV (UTF-8 con BOM)** compatible directamente con Microsoft Excel.
- **Interfaz Web incluida**:
  - Dashboard interactivo con KPIs, carrito POS, gestión de inventario, caja y vista de comprobante sin dependencias pesadas de compilación.

## Arquitectura del proyecto

```text
stockflow-pos/
├── .agents/skills/              # Skills de arquitectura y reglas de negocio POS
├── AGENTS.md                    # Reglas generales del repositorio
├── Dockerfile                   # Imagen lista para producción con uv
├── docker-compose.yml           # Orquestación API + PostgreSQL 16
├── .env.example                 # Plantilla de variables de entorno
├── src/stockflow_pos/
│   ├── main.py                  # Entrada FastAPI, lifespan, seed y frontend
│   ├── core/
│   │   ├── config.py            # Configuración tipada con pydantic-settings
│   │   ├── database.py          # Engine y sesiones SQLAlchemy
│   │   ├── security.py          # Hash PBKDF2 y autenticación JWT por roles
│   │   └── seed.py              # Usuarios y productos demo iniciales
│   ├── models/entities.py       # Tablas: users, products, sales, sale_items, cash_sessions
│   ├── schemas/pos.py           # Esquemas Pydantic v2
│   ├── services/pos_service.py  # Lógica de negocio (stock atómico, IGV, caja, CSV)
│   ├── routers/api.py           # Endpoints REST protegidos por rol
│   └── static/                  # Interfaz web (index.html, styles.css, app.js)
└── tests/
    ├── conftest.py              # Base de datos SQLite en memoria aislada
    └── test_pos_api.py          # Pruebas de integración completas
```

## Usuarios de prueba (creados automáticamente al iniciar)

| Rol | Usuario | Contraseña | Permisos |
| :--- | :--- | :--- | :--- |
| Administrador | `admin` | `admin123` | Todo (productos, reposición, caja, ventas y reportes CSV) |
| Cajero | `cajero` | `cajero123` | Catálogo, apertura/cierre de caja y ventas POS |

## Instalación y ejecución local (SQLite)

Asegúrate de tener [`uv`](https://docs.astral.sh/uv/) instalado:

```bash
git clone https://github.com/DavidG-20/stockflow-pos.git
cd stockflow-pos
cp .env.example .env
uv sync
uv run uvicorn stockflow_pos.main:app --reload
```

- **Aplicación web POS**: `http://localhost:8000`
- **Documentación Swagger API**: `http://localhost:8000/docs`

## Ejecución con Docker + PostgreSQL

```bash
docker compose up --build
```

## Ejecutar pruebas automatizadas

```bash
uv run pytest -v
```

## Licencia

MIT
