---
name: arquitectura-pos
description: Reglas de separación de capas para el sistema Full-Stack stockflow-pos.
---

# Arquitectura del Sistema POS

- **`core/`**: configuración (`config.py`), base de datos (`database.py`), seguridad JWT y hash de contraseñas (`security.py`) y datos iniciales (`seed.py`).
- **`models/`**: modelos ORM de SQLAlchemy (`users`, `products`, `sales`, `sale_items`, `cash_sessions`).
- **`schemas/`**: esquemas Pydantic v2 para validación de entrada y salida.
- **`services/`**: lógica de negocio pura (control de stock atómico, alertas de vencimiento, cálculo de IGV, cuadre de caja, generación de CSV).
- **`routers/`**: endpoints HTTP y control de acceso por roles (`admin` vs `cashier`).
- **`static/`**: interfaz web limpia servida por FastAPI (`index.html`, `styles.css`, `app.js`).
