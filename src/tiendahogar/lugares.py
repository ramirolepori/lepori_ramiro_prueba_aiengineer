"""Plazo de envío según el lugar (Doc 3), resuelto por código y no por el modelo.

El documento solo dice "la capital: 2-3 días hábiles", "otras ciudades: 5-7 días hábiles" e "internacionales: no
disponibles". Un modelo de lenguaje tiene que adivinar qué ciudad es "la capital" (y adivina distinto cada vez), así
que esa decisión se toma acá, con un gazetteer chico (`data/lugares.json`) y reglas explícitas:

- "la capital" = la Ciudad de Buenos Aires (CABA), la capital del país. Decisión de diseño, documentada en SUBMISSION.md.
- "Córdoba capital", "Mendoza capital" o "capital de Salta" son capitales provinciales: no son "la capital" del
  documento, así que cuentan como otras ciudades.
- "Buenos Aires" a secas es ambiguo (la Ciudad o la provincia): se informan los dos plazos y se pide aclarar.
- Los países y ciudades del exterior se resuelven como "envíos internacionales no disponibles".
- Un lugar que no está en el gazetteer pero aparece tras una pista fuerte ("soy de X", "envían a X") se reconoce como
  desconocido y no se adivina.
En producción el lugar sale de la dirección de entrega del cliente, no del texto de la consulta.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PLAZO_CAPITAL = "2-3 días hábiles"
PLAZO_OTRAS = "5-7 días hábiles"
CAPITAL = "la Ciudad de Buenos Aires (CABA)"
CAPITAL_EN_PARENTESIS = "la Ciudad de Buenos Aires, CABA"


@dataclass(frozen=True)
class Lugar:
    nombre: str
    tipo: str                         # capital | otra | exterior | ambiguo_ba | desconocido
    barrio: bool = False              # un barrio de la Ciudad de Buenos Aires
    capital_provincial: bool = False  # "Córdoba capital": capital de su provincia, no del país


def plegar(texto: str) -> str:
    """Minúsculas sin tildes, con la misma longitud que el original (para ubicar el texto original)."""
    salida = []
    for ch in unicodedata.normalize("NFC", texto):
        base = "".join(c for c in unicodedata.normalize("NFD", ch) if not unicodedata.combining(c)).lower()
        salida.append(base[:1] if base else " ")
    return "".join(salida)


@lru_cache(maxsize=1)
def _gazetteer() -> list[tuple[str, str, str, bool]]:
    """(alias plegado, nombre a mostrar, tipo, necesita pista), de más largo a más corto."""
    datos = json.loads((Path(__file__).parent / "data" / "lugares.json").read_text(encoding="utf-8"))
    tipos = {"caba": ("capital", False), "caba_barrios": ("barrio", True), "buenos_aires_ambiguo": ("ambiguo_ba", False),
             "argentina": ("otra", False), "argentina_con_pista": ("otra", True), "exterior": ("exterior", False)}
    entradas = []
    for clave, (tipo, pista) in tipos.items():
        for fila in datos[clave]:
            nombre, *alias = fila.split("|")
            for a in {plegar(nombre), *(plegar(x) for x in alias)}:
                entradas.append((a, nombre, tipo, pista))
    entradas.sort(key=lambda e: -len(e[0]))
    return entradas


@lru_cache(maxsize=1)
def _palabras_simples() -> dict[str, tuple[str, str]]:
    """Alias de una sola palabra de 6+ letras (para tolerar una falta de ortografía: 'cordova', 'tucuman')."""
    return {a: (n, t) for a, n, t, pista in _gazetteer() if not pista and " " not in a and len(a) >= 6 and a.isalpha()}


def _compilar(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])")


_DINERO = re.compile(r"devol|reembols|reintegr|\bpag|cobr|gast|dinero|perd|recuper|vuelta|\bmi\b|\btu\b|\bsu\b")
_ART = r"(?:el |la |los |las )?"
_PISTA = re.compile(rf"(?:\ben|\ba|\bde|\bdesde|\bhacia|\bpara|\bpor|\bbarrio|\bzona)\s+{_ART}$")
_DE_LA_PROVINCIA = re.compile(r"\s+(?:del|de)\s+(?:(?:la\s+)?provincia\s+de\s+|la\s+)?")
_CAPITAL_DEL_PAIS = re.compile(r"\bcapital\s+(?:del\s+pais|nacional|argentina|de\s+argentina|de\s+la\s+argentina|de\s+la\s+nacion)\b")
_CAPITAL = re.compile(r"\bcapital\b")
_DESCONOCIDO = re.compile(
    r"\b(?:soy de|somos de|vivo en|vivimos en|estoy en|estamos en|resido en|vivo por|envios? a|enviar a|envian a|mandan a|"
    r"mandar a|mandas a|llegan? a|entregan en|entregan a|reparten en)\s+"
    r"(?!(?:mi|mis|su|sus|el|la|los|las|un|una|otro|otra|esa|ese|casa|domicilio|direccion|ahi|aca|alla|donde|todo|todos|"
    r"cualquier|tu|tus|nuestra|nuestro)\b)"
    r"([a-z]+(?:\s+(?:de |del |la |los |las |san |santa )?[a-z]+){0,2})")
_CORTE = {"y", "o", "e", "u", "que", "cuanto", "cuantos", "cuantas", "cuando", "como", "se", "me", "tarda", "tardan", "demora",
          "demoran", "llega", "llegan", "en", "a", "con", "por", "para", "si", "pero", "no", "es", "esta", "tarda", "dias", "cuantos"}


def resolver_lugares(texto: str) -> list[Lugar]:
    """Lugares nombrados en la consulta, ya clasificados. Lista vacía si no nombra ninguno."""
    original = unicodedata.normalize("NFC", texto)
    p = plegar(original)
    ocupado = [False] * len(p)
    menciones: list[list] = []        # [inicio, fin, nombre, tipo]
    for alias, nombre, tipo, necesita_pista in _gazetteer():
        for m in _compilar(alias).finditer(p):
            i, f = m.span()
            if any(ocupado[i:f]):
                continue
            if necesita_pista and not _PISTA.search(p[max(0, i - 16):i]):
                continue
            if alias == "la plata" and _DINERO.search(p[max(0, i - 40):i]):
                continue                  # "devolverme la plata" es plata de dinero, no la ciudad de La Plata
            menciones.append([i, f, nombre, tipo])
            ocupado[i:f] = [True] * (f - i)
    for m in re.finditer(r"[a-z]{6,}", p):         # una falta de ortografía en el nombre de la ciudad
        i, f = m.span()
        if any(ocupado[i:f]):
            continue
        cerca = difflib.get_close_matches(m.group(), _palabras_simples(), n=1, cutoff=0.86)
        if cerca:
            nombre, tipo = _palabras_simples()[cerca[0]]
            menciones.append([i, f, nombre, tipo])
            ocupado[i:f] = [True] * (f - i)
    menciones.sort()

    # "Córdoba capital" / "capital de Salta" / "Buenos Aires capital" / "capital federal" / "la capital" a secas
    capital_libre = False
    consumido: set[int] = set()
    marcas: dict[int, bool] = {}
    for c in _CAPITAL.finditer(p):
        i, f = c.span()
        if ocupado[i]:                                   # ya es parte de "capital federal"
            continue
        if _CAPITAL_DEL_PAIS.match(p, i):
            capital_libre = True
            continue
        previa = next((k for k, m in enumerate(menciones) if m[1] <= i and re.fullmatch(r"[\s,(]*", p[m[1]:i])), None)
        posterior = next((k for k, m in enumerate(menciones) if m[0] >= f and _DE_LA_PROVINCIA.fullmatch(p[f:m[0]])), None)
        k = previa if previa is not None else posterior
        if k is not None and k not in consumido:
            consumido.add(k)
            if menciones[k][3] == "ambiguo_ba":
                menciones[k][2:4] = [CAPITAL, "capital"]      # "Buenos Aires capital"
            elif menciones[k][3] == "otra":
                marcas[k] = True
        else:
            capital_libre = True

    exterior = any(m[3] == "exterior" for m in menciones)
    lugares: list[Lugar] = []
    for k, (i, f, nombre, tipo) in enumerate(menciones):
        if tipo == "otra" and exterior and not re.search(r"\bargentina\b", p):
            continue            # "Córdoba, España": el país nombrado manda
        if tipo == "barrio":
            lugares.append(Lugar(nombre, "capital", barrio=True))
        elif tipo == "otra":
            lugares.append(Lugar(nombre, "otra", capital_provincial=marcas.get(k, False)))
        else:
            lugares.append(Lugar(nombre, tipo))
    if capital_libre and not any(l.tipo == "capital" for l in lugares):
        lugares.append(Lugar("la capital", "capital"))

    if not lugares:      # lugar que no está en el gazetteer, pero que la persona dijo con una pista fuerte
        m = _DESCONOCIDO.search(p)
        if m:
            palabras = m.group(1).split()
            while palabras and palabras[-1] in _CORTE:
                palabras.pop()
            for k, w in enumerate(palabras):
                if w in _CORTE and k > 0:
                    palabras = palabras[:k]
                    break
            if palabras and palabras[0] not in _CORTE:
                i = m.start(1)
                dicho = original[i:i + len(" ".join(palabras))].strip(" ,.;!?")
                lugares.append(Lugar(dicho.title() if dicho.islower() else dicho, "desconocido"))
    vistos: set[tuple] = set()
    return [l for l in lugares if not (l in vistos or vistos.add(l))][:3]


def _linea(l: Lugar) -> str:
    if l.tipo == "capital":
        if l.barrio:
            return f"{l.nombre} está en {CAPITAL}, la capital del país: los envíos tardan {PLAZO_CAPITAL}."
        if l.nombre == "la capital":
            return f"Entiendo \"la capital\" como {CAPITAL}: los envíos tardan {PLAZO_CAPITAL}."
        return f"{l.nombre[0].upper() + l.nombre[1:]} es la capital del país: los envíos tardan {PLAZO_CAPITAL}."
    if l.tipo == "otra":
        if l.capital_provincial:
            return (f"{l.nombre} capital es la capital de su provincia, no la del país ({CAPITAL_EN_PARENTESIS}), así que cuenta como "
                    f"otra ciudad: el envío tarda {PLAZO_OTRAS}.")
        return (f"Los envíos a {l.nombre} se consideran envíos a otras ciudades (distintas de la capital, {CAPITAL_EN_PARENTESIS}) y "
                f"tardan {PLAZO_OTRAS}.")
    if l.tipo == "ambiguo_ba":
        return (f"¿Estás en {CAPITAL}? Si es así, el envío tarda {PLAZO_CAPITAL}; si estás en otra localidad de la "
                f"provincia de Buenos Aires (por ejemplo del Gran Buenos Aires o La Plata), tarda {PLAZO_OTRAS}.")
    if l.tipo == "exterior":
        return f"No hacemos envíos a {l.nombre}: los envíos internacionales no están disponibles actualmente."
    return (f"No ubico \"{l.nombre}\". ¿Es una ciudad de Argentina fuera de {CAPITAL}? Si es así, el envío tarda "
            f"{PLAZO_OTRAS}.")


def confirmacion(lugares: list[Lugar]) -> tuple[Lugar | None, Lugar | None] | None:
    """Si la respuesta es una pregunta de sí o no, qué lugar queda con un sí y con un no (None: hay que preguntar de
    nuevo). Devuelve None si no se le preguntó nada al cliente (hay un solo lugar claro, o varios)."""
    if len(lugares) != 1:
        return None
    l = lugares[0]
    if l.tipo == "ambiguo_ba":
        return Lugar(CAPITAL, "capital"), Lugar("la provincia de Buenos Aires", "otra")
    if l.tipo == "desconocido":
        return Lugar(l.nombre, "otra"), None
    return None


PREGUNTA_LUGAR = "¿En qué ciudad y país estás? Con eso te confirmo el plazo."


def respuesta_envio(lugares: list[Lugar]) -> str:
    """Respuesta determinística para uno o más lugares (con la cita del documento)."""
    return " ".join(_linea(l) for l in lugares) + " [envios]"


def respuesta_envio_sin_lugar(preguntar: bool = True) -> str:
    texto = (f"Los envíos a la capital ({CAPITAL_EN_PARENTESIS}) tardan {PLAZO_CAPITAL} y a otras ciudades {PLAZO_OTRAS}. "
             f"Los envíos internacionales no están disponibles actualmente.")
    return f"{texto} {PREGUNTA_LUGAR if preguntar else ''}".strip() + " [envios]"
