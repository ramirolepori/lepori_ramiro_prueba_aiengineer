"""Extracción de montos de dinero de un texto en español, tolerante a formatos.

Entiende: `$600`, `600 USD`, `1.200`, `1,200.50`, `$ 1 200`, `2k`, `1.5k`, `2 mil`, `mil quinientos`,
`quinientos un dólares`, `seiscientos cincuenta pesos` y errores de ortografía leves en los números escritos.
Ignora lo que no es dinero: plazos (`30 días`), cantidades (`2 productos`), porcentajes y números de pedido.
"""

from __future__ import annotations

import difflib
import re
import unicodedata


def _sin_tildes(texto: str) -> str:
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


_UNIDADES = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21,
    "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
}
_CENTENAS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400, "quinientos": 500,
    "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}
_PALABRAS_NUMERO = {**_UNIDADES, **_CENTENAS}
_MONEDAS = {"dolar", "dolares", "usd", "us", "peso", "pesos", "euro", "euros", "eur", "sol", "soles", "usd$"}
_NO_DINERO = {"dia", "dias", "mes", "meses", "hora", "horas", "semana", "semanas", "ano", "anos", "minuto",
              "minutos", "unidad", "unidades", "producto", "productos", "articulo", "articulos", "vez", "veces",
              "kg", "litro", "litros", "cuota", "cuotas", "persona", "personas", "%"}
_PREFIJO_ID = {"pedido", "orden", "ord", "nro", "numero", "num", "n"}

_RE_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[a-z]+|[$%]")


def _parsear_numero(s: str) -> float | None:
    """'1.200' y '1,200' son miles; '500.50' y '500,5' son decimales; '1.200,50' y '1,200.50' mezclan ambos."""
    s = s.strip(".,")
    if not s:
        return None
    if "." in s and "," in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        partes = s.split(sep)
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):
            s = "".join(partes)
        else:
            s = ".".join(partes)
    try:
        return float(s)
    except ValueError:
        return None


def _como_palabra_numero(tok: str) -> str | None:
    """Palabra de número, tolerando género (quinientas) y faltas leves (seicientos)."""
    if tok in _PALABRAS_NUMERO:
        return tok
    if tok.endswith("as") and tok[:-2] + "os" in _PALABRAS_NUMERO:
        return tok[:-2] + "os"
    if len(tok) >= 6:
        cerca = difflib.get_close_matches(tok, [p for p in _PALABRAS_NUMERO if len(p) >= 6], n=1, cutoff=0.86)
        if cerca:
            return cerca[0]
    return None


def _leer_numero_en_palabras(toks: list[str], i: int) -> tuple[float, int] | None:
    """Lee 'mil quinientos', 'dos mil', 'treinta y cinco' desde toks[i]. Devuelve (valor, índice siguiente)."""
    total = actual = 0
    j, leyo = i, False
    while j < len(toks):
        t = toks[j]
        pal = _como_palabra_numero(t)
        if pal is not None:
            actual += _PALABRAS_NUMERO[pal]
            leyo = True
        elif t == "mil":
            total += max(actual, 1) * 1000
            actual, leyo = 0, True
        elif t in {"millon", "millones"}:
            total += max(actual, 1) * 1_000_000
            actual, leyo = 0, True
        elif t == "y" and leyo and j + 1 < len(toks) and _como_palabra_numero(toks[j + 1]) is not None:
            pass
        else:
            break
        j += 1
    return (total + actual, j) if leyo else None


def extraer_montos(texto: str) -> list[float]:
    t = _sin_tildes(texto)
    t = re.sub(r"\bord-\d+\b", " ", t)
    # "1 200" y "$ 1 200 000" son miles separados por espacios
    t = re.sub(r"(?<![\d.,])(\d{1,3})((?: \d{3})+)(?![\d])", lambda m: m.group(1) + m.group(2).replace(" ", ""), t)
    toks = _RE_TOKEN.findall(t)
    montos: list[float] = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        previo = toks[i - 1] if i else ""
        previo2 = toks[i - 2] if i > 1 else ""
        if tok[0].isdigit():
            valor = _parsear_numero(tok)
            j = i + 1
            if valor is not None:
                if j < len(toks) and toks[j] == "k":
                    valor, j = valor * 1000, j + 1
                elif j < len(toks) and toks[j] == "mil":
                    valor, j = valor * 1000, j + 1
                elif j < len(toks) and toks[j] in {"millon", "millones"}:
                    valor, j = valor * 1_000_000, j + 1
                siguiente = toks[j] if j < len(toks) else ""
                con_moneda = previo in {"$", "usd", "us"} or siguiente in _MONEDAS or siguiente == "$"
                es_id = previo in _PREFIJO_ID or (previo == "n" and previo2 in _PREFIJO_ID)
                if con_moneda or (siguiente not in _NO_DINERO and not es_id):
                    montos.append(valor)
            i = j
        elif tok == "mil" or _como_palabra_numero(tok) is not None:
            leido = _leer_numero_en_palabras(toks, i)
            if leido is None:
                i += 1
                continue
            valor, j = leido
            siguiente = toks[j] if j < len(toks) else ""
            # "un", "una", "dos"... sueltos son artículos o cantidades, no dinero, salvo que sigan con una moneda
            if (valor >= 10 or siguiente in _MONEDAS) and siguiente not in _NO_DINERO and previo not in _PREFIJO_ID:
                montos.append(float(valor))
            i = j
        else:
            i += 1
    return montos
