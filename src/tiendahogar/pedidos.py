"""Tool `consultar_estado_pedido` sobre la tabla mock del enunciado."""

from __future__ import annotations

import re
from typing import Any

PEDIDOS: dict[str, dict[str, str]] = {
    "ORD-1001": {"producto": "Refrigeradora", "estado": "En tránsito", "entrega_estimada": "3 días hábiles"},
    "ORD-1002": {"producto": "Licuadora", "estado": "Entregado", "entrega_estimada": "—"},
    "ORD-1003": {"producto": "Lavadora", "estado": "Procesando", "entrega_estimada": "6 días hábiles"},
    "ORD-1004": {"producto": "Tostadora", "estado": "Cancelado", "entrega_estimada": "—"},
}

NO_ENCONTRADO = "No encontrado"

_RE_ID = re.compile(r"\bORD-\d{1,8}\b", re.IGNORECASE)


def consultar_estado_pedido(order_id: str) -> dict[str, Any]:
    """Devuelve los datos del pedido, o `estado: "No encontrado"` si el id no existe. Nunca inventa datos.

    Solo se normaliza mayúsculas y espacios en los bordes ("ord-1001 " vale como "ORD-1001").
    """
    clave = order_id.strip().upper() if isinstance(order_id, str) else ""
    datos = PEDIDOS.get(clave)
    if datos is None:
        return {"order_id": order_id, "encontrado": False, "estado": NO_ENCONTRADO,
                "mensaje": "No existe un pedido con ese número en el sistema."}
    return {"order_id": clave, "encontrado": True, **datos}


def extraer_order_ids(texto: str) -> list[str]:
    """Ids con forma ORD-<números> mencionados en el texto, en mayúsculas y sin repetir."""
    return list(dict.fromkeys(m.upper() for m in _RE_ID.findall(texto)))


ESQUEMA_TOOL = {
    "nombre": "consultar_estado_pedido",
    "descripcion": "Devuelve producto, estado y entrega estimada de un pedido a partir de su número (ORD-XXXX).",
    "parametros": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
}
