---
name: reglas-negocio-pos
description: Reglas obligatorias de integridad financiera, inventario y seguridad en stockflow-pos.
---

# Reglas de Negocio y Seguridad POS

- **Stock nunca negativo**: toda venta debe verificar stock suficiente de todos los ítems antes de descontar en una sola transacción; si falta stock, rechaza con `409 Conflict` sin modificar ningún producto.
- **Cálculo tributario**: el precio del producto incluye IGV (18% en Perú); el comprobante desglosa `subtotal`, `igv` y `total` con redondeo a 2 decimales (`Decimal`).
- **Control de caja**: solo puede haber una sesión de caja abierta por usuario a la vez; al cerrar, calcula `expected_amount` y `difference` automáticamente.
- **Control de roles**: solo `admin` puede crear productos, reponer stock o exportar reportes; `cashier` puede consultar catálogo, operar su caja y registrar ventas.
- **Pruebas aisladas**: todos los tests de `pytest` corren contra SQLite en memoria (`StaticPool`).
