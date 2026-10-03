"""Lo que el cliente ya dijo en la conversación y puede volver a preguntar ("cómo me llamo?", "cuál fue la orden que te
pasé?", "en qué ciudad dije que estaba?").

La sesión guarda un diccionario chico de datos que el cliente dio él mismo, ya pasados por los extractores del agente: el
nombre (validado), el número de pedido (normalizado a ORD-XXXX), el lugar (solo uno reconocido) y el monto (un número).
Nunca se guarda ni se repite texto libre, y las respuestas salen de plantillas fijas, así que esto no abre un camino para
meter instrucciones ni para ver datos de otra persona: lo único que se puede recuperar es lo que esa misma sesión puso.
"""

from __future__ import annotations

import re

from .lugares import resolver_lugares
from .montos import extraer_montos
from .pedidos import extraer_referencias
from .rag import normalizar

_RECUERDO = {"nombre": "Te llamás {}.", "pedido": "El pedido que me pasaste es {}.",
             "lugar": "Me dijiste que estás en {}.", "monto": "El monto que me dijiste es ${}."}
_SIN_DATO = {"nombre": "Todavía no me dijiste tu nombre. Si querés, decime cómo te llamás.",
             "pedido": "Todavía no me pasaste ningún número de pedido.",
             "lugar": "Todavía no me dijiste dónde estás.",
             "monto": "Todavía no me dijiste ningún monto."}

_PREGUNTAS = {
    "nombre": re.compile(r"como me llamo|cual es mi nombre|como es mi nombre|sabes (?:mi nombre|como me llamo)|"
                         r"te acordas de mi nombre|recordas mi nombre|(?:decime|dime) mi nombre"),
    "pedido": re.compile(r"\b(?:que|cual|cuales)\b.{0,25}\b(?:orden|ordenes|pedido|pedidos|numero)\b.{0,30}"
                         r"\b(?:pase|di|dije|escribi|mande|mencione|consulte|use|puse)\b|"
                         r"cual era (?:mi|el) (?:pedido|orden|numero de pedido)|que (?:pedido|orden) (?:consulte|mire|vimos)|"
                         r"(?:te acordas|recordas|sabes) (?:cual|que|mi) .{0,20}(?:pedido|orden)"),
    "lugar": re.compile(r"\b(?:donde|de donde|en que (?:ciudad|lugar))\b.{0,25}\b(?:vivo|estoy|dije|mencione)\b|"
                        r"cual era (?:mi|la) (?:ciudad|localidad)|que (?:ciudad|lugar) te (?:dije|pase|mencione)"),
    "monto": re.compile(r"\bcuanto\b.{0,25}\b(?:era|fue|dije)\b.{0,25}\b(?:monto|reembolso|compra|plata|importe)\b|"
                        r"que monto te (?:dije|pase|mencione)|cual era (?:el|mi) monto"),
}
_LUGARES_RECONOCIDOS = {"capital", "otra", "exterior"}


def clave_del_recuerdo(mensaje: str) -> str | None:
    """Qué dato de la conversación pide el cliente que le recuerden, si es eso lo que pide."""
    t = normalizar(mensaje)
    return next((clave for clave, patron in _PREGUNTAS.items() if patron.search(t)), None)


def responder_recuerdo(datos: dict[str, str] | None, clave: str) -> str:
    valor = (datos or {}).get(clave)
    return _RECUERDO[clave].format(valor) if valor else _SIN_DATO[clave]


def anotar(datos: dict[str, str], mensaje: str) -> None:
    """Guarda lo que `mensaje` dice del pedido, el lugar o el monto (lo último que dijo pisa lo anterior). El nombre se
    guarda aparte, cuando se presenta al saludar."""
    refs = extraer_referencias(mensaje)
    if refs:
        datos["pedido"] = refs[-1][0]
    lugares = [l for l in resolver_lugares(mensaje) if l.tipo in _LUGARES_RECONOCIDOS]
    if lugares:
        datos["lugar"] = lugares[-1].nombre
    montos = extraer_montos(mensaje)
    if montos:
        datos["monto"] = f"{montos[-1]:,.0f}".replace(",", ".")
