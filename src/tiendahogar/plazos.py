"""Cuánto hace que el cliente compró (o cuánto tiene el producto), cuando lo dice, para aplicar con una cuenta el plazo de
devolución del Doc 2 y el de la garantía del Doc 1 en lugar de la palabra de un modelo chico (que a veces razona mal: "no se
aceptan devoluciones después de 30 días si el producto no fue usado", o "no podés devolverla" con la garantía vigente).

Reconoce "compré hace 45 días", "hace 3 semanas", "compré ayer", "mi lavadora tiene 8 meses", "una plancha de 3 meses" y "una
lavadora de hace 40 días". No cuenta si el número es de otra cosa: los días de espera de un reembolso, "hace 3 días se me rompió"
(la fecha de la falla, no de la compra) o "tiene 6 meses de garantía" (el plazo de la garantía, no la edad del producto)."""

from __future__ import annotations

import re
import unicodedata

PLAZO_DEVOLUCION_DIAS = 30

_NUMEROS = {"un": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
            "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "veinte": 20, "treinta": 30,
            "cuarenta": 40, "cincuenta": 50, "sesenta": 60}
_UNIDAD = {"dia": 1, "dias": 1, "semana": 7, "semanas": 7, "mes": 30, "meses": 30, "ano": 365, "anos": 365}
_NUM = r"(\d+|" + "|".join(_NUMEROS) + r")"
_UNIDADES = r"(dias?|semanas?|meses|mes|anos?)"

# Productos del Doc 1, por una raíz que sirve para el singular, el plural y el género ("refrigerador" y "refrigeradora"), con el
# nombre con que se le habla al cliente y los meses de garantía: 12 los electrodomésticos grandes y 6 los pequeños
_PRODUCTOS = {"refrigerador": ("refrigeradora", 12), "heladera": ("heladera", 12), "nevera": ("nevera", 12),
              "lavadora": ("lavadora", 12), "lavarropas": ("lavarropas", 12), "estufa": ("estufa", 12),
              "licuadora": ("licuadora", 6), "plancha": ("plancha", 6), "tostadora": ("tostadora", 6)}
_NOMBRES = "|".join(_PRODUCTOS) + "|producto|equipo|aparato|electrodomestico"

_DURACION = re.compile(r"\b(?:hace|hacen|pasaron|pasaron como|hace unos|hace como|hace casi|hace mas de)\s+" + _NUM + r"\s+" + _UNIDADES + r"\b")
# La edad del producto dicha como "mi lavadora tiene 8 meses", "una plancha de 3 meses" o "una lavadora de hace 40 días"
_EDAD = re.compile(r"\b(?:" + _NOMBRES + r")\w*(?:\s+[a-z]+){0,4}?\s+(?:tiene|tienen)(?: unos| como| casi| mas de)?\s+" + _NUM +
                   r"\s+" + _UNIDADES + r"\b(?!\s+de\s+garantia)")
_DE_EDAD = re.compile(r"\b(?:" + _NOMBRES + r")\w*\s+(?:que (?:tengo|compre|compramos)\s+)?de\s+(?:hace\s+)?" + _NUM +
                      r"\s+" + _UNIDADES + r"\b(?!\s+de\s+garantia)")
_GARANTIA_DE = re.compile(r"garantia (?:de|del)\s+(?:(?:la|el|mi|un|una|su)\s+)?$")
_COMPRO = re.compile(r"\b(?:compr\w+|adquir\w+|ordene|pedi|encargue|me llego|recibi|antiguedad)\b")
_QUIERE_DEVOLVER = re.compile(r"\b(?:devolver\w*|devuelv\w*|devolucion|cambiar\w*|cambio|retorno)\b|de vuelta")
_ESPERA_UN_REEMBOLSO = re.compile(r"reembols|reintegr|impact|tarjeta|dinero|plata|acredit")
# Habla de la garantía o de una falla: lo que lleva a mirar el plazo de la garantía aunque no diga la palabra
_FALLA = re.compile(r"garant|rompi|descompus|fall[oa]\w*|defect\w+|averi|quem[oa]|"
                    r"no (?:funciona|anda|enciende|prende|arranca|calienta|enfria|lava|licua|tuesta|centrifuga)")
_MESES_POR_UNIDAD = {"dia": 1 / 30, "dias": 1 / 30, "semana": 7 / 30, "semanas": 7 / 30, "mes": 1, "meses": 1, "ano": 12, "anos": 12}
_UNIDAD_ESCRITA = {"dia": "día", "dias": "días", "ano": "año", "anos": "años"}


def _sin_tildes(texto: str) -> str:
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _numero(m: re.Match) -> int:
    return int(m.group(1)) if m.group(1).isdigit() else _NUMEROS[m.group(1)]


def _tiempo_de_uso(t: str) -> re.Match | None:
    """Cuánto hace que compró o cuánto tiene el producto, sobre el texto sin tildes. Un "hace N días" suelto solo cuenta si la
    frase habla de comprar: puede ser la fecha de la falla o los días que lleva esperando un reembolso."""
    m = _EDAD.search(t)
    if m is None:
        m = _DE_EDAD.search(t)
        if m is not None and _GARANTIA_DE.search(t[:m.start()]):
            m = None         # "la garantía de la plancha de 6 meses": puede ser el plazo de la garantía y no la edad de la plancha
    if m is None and _COMPRO.search(t):
        m = _DURACION.search(t)
    return m


def dias_desde_la_compra(texto: str) -> int | None:
    """Días desde la compra si la frase pide devolver o cambiar algo y da una duración. Si no, None."""
    t = _sin_tildes(texto)
    if not _QUIERE_DEVOLVER.search(t) or _ESPERA_UN_REEMBOLSO.search(t):
        return None
    if re.search(r"\bcompr\w+ (?:hoy|recien)\b", t):
        return 0
    if re.search(r"\b(?:compr\w+|adquir\w+) ayer\b|\bayer (?:compr\w+|adquir\w+|fui\b.*\bcompr\w+|hice una compra)", t):
        return 1
    m = _tiempo_de_uso(t)
    return None if m is None else _numero(m) * _UNIDAD[m.group(2)]


def nota_de_devolucion(dias: int) -> str:
    """Lo que dice el Doc 2 aplicado a esos días. Repite el documento, no agrega ninguna regla."""
    if dias > PLAZO_DEVOLUCION_DIAS:
        return (f"Como pasaron más de {PLAZO_DEVOLUCION_DIAS} días desde la compra, la devolución solo se acepta si el "
                f"producto tiene un defecto cubierto por la garantía.")
    return (f"Como estás dentro de los {PLAZO_DEVOLUCION_DIAS} días desde la compra, la devolución se acepta si el producto "
            f"está sin usar y en su empaque original.")


def garantia_del_producto(texto: str, devolucion: bool = False, requiere_motivo: bool = True) -> str | None:
    """Si el cliente nombra un producto del Doc 1 y cuánto hace que lo tiene, aplica el plazo de su garantía con una cuenta (12
    meses los grandes, 6 los pequeños). Repite el documento: no agrega ninguna regla. Sin un producto (o con dos de plazos
    distintos) o sin tiempo, None. Con `requiere_motivo` pide además que hable de la garantía o de una falla. Con `devolucion`,
    si el plazo ya pasó, dice qué implica para la devolución (pasados los 30 días solo se acepta un defecto cubierto)."""
    t = _sin_tildes(texto)
    if requiere_motivo and not _FALLA.search(t):
        return None
    productos = {nombre: meses for raiz, (nombre, meses) in _PRODUCTOS.items() if raiz in t}
    m = _tiempo_de_uso(t)
    if len(productos) != 1 or m is None:
        return None
    (producto, plazo), = productos.items()
    meses = _numero(m) * _MESES_POR_UNIDAD[m.group(2)]
    cuanto = f"{m.group(1) if m.group(1).isdigit() else _numero(m)} {_UNIDAD_ESCRITA.get(m.group(2), m.group(2))}"
    if meses <= plazo:
        return (f"La garantía de tu {producto} es de {plazo} meses desde la fecha de compra: con {cuanto} "
                f"todavía estás dentro de ese plazo. La garantía cubre defectos de fábrica, no daños por mal uso.")
    vencida = f"La garantía de tu {producto} es de {plazo} meses desde la fecha de compra, y con {cuanto} ya pasó ese plazo."
    return f"{vencida[:-1]}, así que la devolución no se acepta." if devolucion else vencida


def respuesta_de_garantia(texto: str) -> str | None:
    """La cuenta de la garantía cuando la pregunta es solo de garantía (ver `garantia_del_producto`)."""
    return garantia_del_producto(texto)
