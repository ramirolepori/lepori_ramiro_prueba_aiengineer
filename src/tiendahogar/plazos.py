"""Cuánto hace que el cliente compró, cuando lo dice, para aplicar el plazo de devolución del Doc 2 con una cuenta y no con
la palabra de un modelo chico (que a veces razona mal: "no se aceptan devoluciones después de 30 días si el producto no
fue usado").

Solo cuenta cuando la frase habla de devolver o cambiar algo que compró y da una duración clara ("hace 45 días", "hace 3
semanas", "compré ayer"). Si el número es de otra cosa (los días que lleva esperando un reembolso) no se usa."""

from __future__ import annotations

import re
import unicodedata

PLAZO_DEVOLUCION_DIAS = 30

_NUMEROS = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
            "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "veinte": 20, "treinta": 30,
            "cuarenta": 40, "cincuenta": 50, "sesenta": 60}
_UNIDAD = {"dia": 1, "dias": 1, "semana": 7, "semanas": 7, "mes": 30, "meses": 30, "ano": 365, "anos": 365}
_NUM = r"(\d+|" + "|".join(_NUMEROS) + r")"
_DURACION = re.compile(r"\b(?:hace|hacen|pasaron|pasaron como|hace unos|hace como|hace casi|hace mas de)\s+" + _NUM +
                       r"\s+(dias?|semanas?|meses|mes|anos?)\b")
_COMPRO = re.compile(r"\b(?:compr\w+|adquir\w+|ordene|pedi|encargue|me llego|recibi|antiguedad)\b")
_QUIERE_DEVOLVER = re.compile(r"\b(?:devolver\w*|devuelv\w*|devolucion|cambiar\w*|cambio|retorno)\b|de vuelta")
_ESPERA_UN_REEMBOLSO = re.compile(r"reembols|reintegr|impact|tarjeta|dinero|plata|acredit")


def _sin_tildes(texto: str) -> str:
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def dias_desde_la_compra(texto: str) -> int | None:
    """Días desde la compra si la frase pide devolver o cambiar algo y da una duración. Si no, None."""
    t = _sin_tildes(texto)
    if not _QUIERE_DEVOLVER.search(t) or not _COMPRO.search(t) or _ESPERA_UN_REEMBOLSO.search(t):
        return None
    if re.search(r"\bcompr\w+ (?:hoy|recien)\b", t):
        return 0
    if re.search(r"\b(?:compr\w+|adquir\w+) ayer\b|\bayer (?:compr\w+|adquir\w+|fui\b.*\bcompr\w+|hice una compra)", t):
        return 1
    m = _DURACION.search(t)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1).isdigit() else _NUMEROS[m.group(1)]
    return n * _UNIDAD[m.group(2)]


def nota_de_devolucion(dias: int) -> str:
    """Lo que dice el Doc 2 aplicado a esos días. Repite el documento, no agrega ninguna regla."""
    if dias > PLAZO_DEVOLUCION_DIAS:
        return (f"Como pasaron más de {PLAZO_DEVOLUCION_DIAS} días desde la compra, la devolución solo se acepta si el "
                f"producto tiene un defecto cubierto por la garantía.")
    return (f"Como estás dentro de los {PLAZO_DEVOLUCION_DIAS} días desde la compra, la devolución se acepta si el producto "
            f"está sin usar y en su empaque original.")
