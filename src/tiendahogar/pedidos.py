"""Tool `consultar_estado_pedido` sobre la tabla mock del enunciado."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

PEDIDOS: dict[str, dict[str, str]] = {
    "ORD-1001": {"producto": "Refrigeradora", "estado": "En tránsito", "entrega_estimada": "3 días hábiles"},
    "ORD-1002": {"producto": "Licuadora", "estado": "Entregado", "entrega_estimada": "—"},
    "ORD-1003": {"producto": "Lavadora", "estado": "Procesando", "entrega_estimada": "6 días hábiles"},
    "ORD-1004": {"producto": "Tostadora", "estado": "Cancelado", "entrega_estimada": "—"},
}

NO_ENCONTRADO = "No encontrado"

def consultar_estado_pedido(order_id: str) -> dict[str, Any]:
    """Devuelve los datos del pedido, o `estado: "No encontrado"` si el id no existe. Nunca inventa datos.

    Solo se normaliza may\u00fasculas y espacios en los bordes ("ord-1001 " vale como "ORD-1001").
    """
    clave = order_id.strip().upper() if isinstance(order_id, str) else ""
    datos = PEDIDOS.get(clave)
    if datos is None:
        return {"order_id": order_id, "encontrado": False, "estado": NO_ENCONTRADO,
                "mensaje": "No existe un pedido con ese n\u00famero en el sistema."}
    return {"order_id": clave, "encontrado": True, **datos}


# Guiones de todo tipo (-, \u2010, \u2011, \u2012, \u2013, \u2014, \u2015, \u2212) y guion bajo
_GUIONES = "\\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212_"
_SEP_ORD = rf"[\s{_GUIONES}.:#]*"
_NO_DINERO = r"(?!\s*(?:dolares|dolar|usd|pesos|euros|dias|dia|meses|horas|semanas|\$|%))"

# "ORD-1001", "ord1001", "ORD 1001", "Ord. 1001", "ORD–1001" (con cualquier tipo de guion)
_RE_ORD = re.compile(rf"(?<![a-z])ord{_SEP_ORD}(\d{{3,8}})\b{_NO_DINERO}")

# "pedido 1001", "mi pedido es el 1001", "pedido nro 1001", "pedido n° 1001", "pedido #1001", "orden de compra 1001",
# "número de pedido: 1001" y listas ("pedidos 1001 y 1004")
_RE_CONTEXTO = re.compile(
    r"\b(?:pedidos?|ordenes|orden)\b[\s:]*"
    r"(?:(?:de (?:pedido|compra|orden)|n[\u00ba\u00b0]|nro\.?|numero|num\.?)[\s:.]*)?"
    r"(?:(?:es|era|seria|son) )?(?:el |la |los )?[\s#:]*(?:ord" + _SEP_ORD + r")?"
    rf"(\d{{3,8}})\b{_NO_DINERO}"
    rf"((?:\s*(?:,|y|e)\s*(?:ord{_SEP_ORD})?\d{{3,8}}\b{_NO_DINERO})*)"
)


def _sin_tildes(texto: str) -> str:
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def extraer_referencias(texto: str) -> list[tuple[str, str]]:
    """Números de pedido mencionados, como (id normalizado `ORD-1001`, texto tal cual lo escribió el cliente).

    Acepta el prefijo `ORD` con cualquier separador y también "pedido 1001", "orden de compra 1001",
    "número de pedido: 1001", "pedido nro 1001", "pedido #1001" y listas ("pedidos 1001 y 1004").
    Un número suelto sin contexto de pedido no cuenta: puede ser un monto o un plazo.
    """
    t = _sin_tildes(texto)
    hallados: list[tuple[int, str, str]] = []
    for m in _RE_ORD.finditer(t):
        hallados.append((m.start(), m.group(1), texto[m.start():m.end()]))
    for m in _RE_CONTEXTO.finditer(t):
        hallados.append((m.start(1), m.group(1), m.group(1)))
        for extra in re.finditer(r"\d{3,8}", m.group(2) or ""):
            hallados.append((m.start(2) + extra.start(), extra.group(0), extra.group(0)))
    vistos: dict[str, str] = {}
    for _, digitos, literal in sorted(hallados):
        vistos.setdefault(f"ORD-{digitos}", literal)
    return list(vistos.items())


def extraer_order_ids(texto: str) -> list[str]:
    """Ids normalizados (ORD-<números>) mencionados en el texto, sin repetir."""
    return [i for i, _ in extraer_referencias(texto)]


ESQUEMA_TOOL = {
    "nombre": "consultar_estado_pedido",
    "descripcion": "Devuelve producto, estado y entrega estimada de un pedido a partir de su número (ORD-XXXX).",
    "parametros": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
}
