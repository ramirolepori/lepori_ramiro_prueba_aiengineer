"""Tool `consultar_estado_pedido` sobre la tabla mock del enunciado."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .montos import _leer_numero_en_palabras

PEDIDOS: dict[str, dict[str, str]] = {
    "ORD-1001": {"producto": "Refrigeradora", "estado": "En tránsito", "entrega_estimada": "3 días hábiles"},
    "ORD-1002": {"producto": "Licuadora", "estado": "Entregado", "entrega_estimada": "—"},
    "ORD-1003": {"producto": "Lavadora", "estado": "Procesando", "entrega_estimada": "6 días hábiles"},
    "ORD-1004": {"producto": "Tostadora", "estado": "Cancelado", "entrega_estimada": "—"},
}

NO_ENCONTRADO = "No encontrado"

_INVISIBLES = dict.fromkeys(map(ord, "​‌‍⁠﻿"))


def _limpiar(texto: str) -> str:
    """Quita lo que se cuela al copiar y pegar: espacios al borde, caracteres invisibles, anchos completos (ＯＲＤ) y guiones raros."""
    t = unicodedata.normalize("NFKC", texto).translate(_INVISIBLES)
    return re.sub("[‐‑‒–—―−]", "-", t).strip()


def consultar_estado_pedido(order_id: str) -> dict[str, Any]:
    """Devuelve los datos del pedido, o `estado: "No encontrado"` si el id no existe. Nunca inventa datos.

    Solo se normaliza may\u00fasculas y espacios en los bordes ("ord-1001 " vale como "ORD-1001").
    """
    clave = _limpiar(order_id).upper() if isinstance(order_id, str) else ""
    datos = PEDIDOS.get(clave)
    if datos is None:
        # se devuelve tal cual lo recibió si es texto; otra cosa (bytes, número) se pasa a texto para que la respuesta sea serializable
        return {"order_id": order_id if isinstance(order_id, str) or order_id is None else str(order_id), "encontrado": False, "estado": NO_ENCONTRADO,
                "mensaje": "No existe un pedido con ese n\u00famero en el sistema."}
    return {"order_id": clave, "encontrado": True, **datos}


# Guiones de todo tipo (-, \u2010, \u2011, \u2012, \u2013, \u2014, \u2015, \u2212) y guion bajo
_GUIONES = "\\-\u2010\u2011\u2012\u2013\u2014\u2015\u2212_"
_SEP_ORD = rf"[\s{_GUIONES}.:#]*"
_NO_DINERO = r"(?!\s*(?:dolares|dolar|usd|pesos|euros|dias|dia|meses|horas|semanas|anos|ano|veces|unidades|productos|\$|%))"

# "ORD-1001", "ord1001", "ORD 1001", "Ord. 1001", "ORD–1001" (con cualquier tipo de guion)
_RE_ORD = re.compile(rf"(?<![a-z])ord{_SEP_ORD}(\d{{3,8}})\b{_NO_DINERO}")

# "pedido 1001", "mi pedido es el 1001", "pedido nro 1001", "pedido n° 1001", "pedido #1001", "orden de compra 1001",
# "número de pedido: 1001" y listas ("pedidos 1001 y 1004")
_RE_CONTEXTO = re.compile(
    r"\b(?:pedidos?|ordenes|orden|compras?|encargos?|transaccion(?:es)?|operacion(?:es)?)\b[\s:]*"
    r"(?:(?:de (?:pedido|compra|orden)|n[\u00ba\u00b0]|nro\.?|numero|num\.?)[\s:.]*)?"
    r"(?:(?:es|era|seria|son) )?(?:el |la |los )?[\s#:]*(?:ord" + _SEP_ORD + r")?"
    rf"(\d{{3,8}})\b{_NO_DINERO}"
    rf"((?:\s*(?:,|y|e)\s*(?:ord{_SEP_ORD})?\d{{3,8}}\b{_NO_DINERO})*)"
)


# "n°2000", "nro 1003", "# 1003" sin decir "pedido": en una consulta de soporte es un número de pedido
_RE_NUMERO_SUELTO = re.compile(rf"(?<![a-z0-9])(?:n[º°]\.?|nro\.?|numero|num\.?|#)\s*[:#]?\s*(\d{{3,6}})\b{_NO_DINERO}")

# Un identificador que parece de pedido pero no tiene el formato ORD-XXXX: "DRO-1002", "ORD1OO1", "ORD-ABCD", "OD-1002"
_RE_RARO = re.compile(
    r"(?<![a-z0-9@])(?:pedidos?|ordenes|orden|compras?|encargos?|transaccion(?:es)?|operacion(?:es)?|ticket|codigo|"
    r"referencia|n[º°]|nro\.?|numero|num\.?|#)"
    r"[\s:.#]*(?:de (?:pedido|compra|orden)[\s:.]*)?(?:(?:es|era|seria)\s+)?(?:el |la )?[\s#:]*"
    r"([a-z0-9]+(?:[-_]+[a-z0-9]+)+|[a-z]{2,8}\d[a-z0-9]*)(?![a-z0-9@.])")
# El mismo tipo de código suelto en cualquier parte de la frase ("ordené una licuadora (DOR--1002) y quería saber el
# estado"): solo si la frase habla de un pedido, para no tomar un modelo de producto por un número de pedido
_RE_CODIGO_SUELTO = re.compile(r"(?<![a-z0-9@])([a-z]{2,6}[-_]{1,2}\d{3,8})(?![a-z0-9@.])")
_HABLA_DE_UN_PEDIDO = re.compile(r"\b(?:ordene|orden|pedido|pedi|compra|compre|adquiri|encargue|estado|seguimiento|numero|nro)\b")


_RE_ORD_PEGADO = re.compile(rf"(?<![a-z0-9])ord{_SEP_ORD}\d{{3,8}}[a-z]\w*")


def _sin_tildes(texto: str) -> str:
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_RE_EN_PALABRAS = re.compile(r"\b(?:pedidos?|ordenes|orden|compras?)\s+(?:(?:de (?:pedido|compra|orden)|numero|nro\w*)\s+)*"
                             r"((?:[a-z]+\s*)+)")


def _numero_en_palabras(texto: str) -> int | None:
    """'mil uno' -> 1001. Solo si todo lo que sigue a 'pedido' son palabras de número."""
    toks = texto.split()
    leido = _leer_numero_en_palabras(toks, 0)
    return int(leido[0]) if leido and leido[1] == len(toks) else None


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
    for m in _RE_NUMERO_SUELTO.finditer(t):
        hallados.append((m.start(1), m.group(1), m.group(1)))
    for m in _RE_EN_PALABRAS.finditer(t):
        valor = _numero_en_palabras(m.group(1))
        if valor is not None and 100 <= valor <= 99999999:
            hallados.append((m.start(1), str(valor), m.group(1).strip()))
    vistos: dict[str, str] = {}
    for _, digitos, literal in sorted(hallados):
        vistos.setdefault(f"ORD-{digitos}", literal)
    return list(vistos.items())


def extraer_identificadores_raros(texto: str) -> list[str]:
    """Identificadores con aspecto de número de pedido pero sin el formato ORD-XXXX (tal cual los escribió el cliente).
    No se corrigen en silencio: el agente dice que no lo encontró y cuál es el formato."""
    t = _sin_tildes(texto)
    raros: list[str] = []
    candidatos = list(_RE_RARO.finditer(t))
    for m in _RE_ORD_PEGADO.finditer(t):
        raros.append(texto[m.start():m.end()])
    if _HABLA_DE_UN_PEDIDO.search(t):
        candidatos += list(_RE_CODIGO_SUELTO.finditer(t))
    for m in candidatos:
        tok = m.group(1)
        if re.fullmatch(r"ord[\s\-_.:#]*\d{3,8}", tok) or tok[0].isdigit():
            continue                                            # ya es un ORD-XXXX válido, o empieza con un número
        partes = re.split(r"[-_]", tok)
        if not (re.search(r"\d", tok) or partes[0].startswith("ord")) or all(x.isdigit() for x in partes):
            continue                                            # una palabra con guion, no un identificador
        literal = texto[m.start(1):m.end(1)]
        if literal not in raros:
            raros.append(literal)
    return raros


def extraer_order_ids(texto: str) -> list[str]:
    """Ids normalizados (ORD-<números>) mencionados en el texto, sin repetir."""
    return [i for i, _ in extraer_referencias(texto)]


ESQUEMA_TOOL = {
    "nombre": "consultar_estado_pedido",
    "descripcion": "Devuelve producto, estado y entrega estimada de un pedido a partir de su número (ORD-XXXX).",
    "parametros": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]},
}
