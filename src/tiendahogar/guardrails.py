"""Guardrails determinísticos: corren ANTES del modelo, así que no dependen de que el LLM obedezca.

Casos que el agente no resuelve (Doc 4 y Doc 5): reembolsos mayores a $500, quejas sobre el trato de un
empleado, disputas de facturación y temas legales. Se escalan a soporte@tiendahogar.example.
Reembolso de exactamente $500 NO escala: el documento dice "mayores a $500".
Además hay una detección simple de intentos de inyección de prompt en la entrada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .rag import normalizar

CONTACTO = "soporte@tiendahogar.example"
TOPE_REEMBOLSO = 500.0

# --- Reglas por categoría (sobre texto sin tildes ni mayúsculas) -----------------------------------------

_LEGAL = re.compile(
    r"\b(demand\w+|abogad\w+|legal\w*|judicial\w*|juicio|tribunal\w*|denunci\w+|querella|indemnizaci\w+|"
    r"fraude|estafa\w*|ilegal\w*|arbitraje|mediacion|incumplimiento|derechos? del consumidor|"
    r"defensa del consumidor|acciones? (?:legal|judicial)\w*)"
)
_TRATO = re.compile(
    r"(maltrat\w+|grosero|grosera|groseria\w*|descortes\w*|destrat\w+|insult\w+|falta de respeto|"
    r"irrespetuos\w+|(?:mala|pesima|horrible) (?:atencion|actitud)|mal trato|trato (?:horrible|pesimo|malo|inadecuado)|"
    r"(?:me )?(?:trat\w+|atendi\w+|respondi\w+|hablo\w*|contesto\w*) (?:muy |super |re )?(?:mal|pesimo|horrible|feo|"
    r"de mala manera)|"
    r"(?:queja|quejar\w*|reclamo|denunciar?)\b.{0,50}\b(?:empleado|empleada|vendedor\w*|agente|asesor\w*|"
    r"repartidor\w*|personal|trato|atencion|cajer\w+|chofer))"
)
_FACTURACION = re.compile(
    r"((?:disput\w+|reclam\w+|impugn\w+|contest\w+|no reconozco)\b.{0,50}\b(?:factura\w*|cobro\w*|cargo\w*)|"
    r"\b(?:factura\w*|cobro\w*|cargo\w*)\b.{0,50}\b(?:incorrect\w+|erroneo\w*|equivocad\w+|indebid\w+|duplicad\w+|"
    r"no autorizad\w+|de mas|demas|por error)|"
    r"(?:me )?(?:cobr\w+|facturar\w*|cargar\w*|debit\w+)\b.{0,40}\b(?:de mas|demas|dos veces|doble|2 veces|por error|"
    r"mal)|"
    r"contracargo|doble cobro|cobro doble|cobro duplicado)"
)
_INTENCION_REEMBOLSO = re.compile(
    r"(reembols\w+|reintegr\w+|refund|devol\w+|devuelv\w+|regres\w+|dinero|plata)"
)
_UNIDADES_TIEMPO = r"(?:dias?|meses|mes|horas?|semanas?|anos?|unidades|unidad|%|kg|litros?)"
_NUMEROS_PALABRA = {"quinientos": 500, "seiscientos": 600, "setecientos": 700, "ochocientos": 800,
                    "novecientos": 900, "mil": 1000}
_RE_NUM = re.compile(
    r"(?P<moneda_pre>\$|usd|us\$|u\$s|eur|€)?\s*(?P<num>\d[\d.,]*\d|\d)(?P<mil>\s*mil\b)?"
    r"\s*(?P<moneda_pos>\$|usd|dolares?|pesos|euros?|€)?(?P<tiempo>\s*" + _UNIDADES_TIEMPO + r"\b)?"
)


@dataclass(frozen=True)
class Escalamiento:
    categoria: str     # "reembolso_mayor_500" | "queja_trato" | "disputa_facturacion" | "tema_legal"
    motivo: str
    mensaje: str       # lo que se le responde al cliente


def _parsear_numero(s: str) -> float | None:
    s = s.strip(".,")
    if not s:
        return None
    if "." in s and "," in s:  # el último separador es el decimal
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        ent = "." if dec == "," else ","
        s = s.replace(ent, "").replace(dec, ".")
    elif "." in s or "," in s:
        sep = "." if "." in s else ","
        partes = s.split(sep)
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3):  # 1.200 / 1.200.000: miles
            s = "".join(partes)
        else:
            s = ".".join(partes)
    try:
        return float(s)
    except ValueError:
        return None


def extraer_montos(texto: str) -> list[float]:
    """Montos de dinero mencionados. Ignora números de pedido, plazos (30 días, 6 meses) y cantidades."""
    t = re.sub(r"\bord-\d+\b", " ", normalizar(texto))
    montos: list[float] = []
    for m in _RE_NUM.finditer(t):
        if m.group("tiempo") and not (m.group("moneda_pre") or m.group("moneda_pos")):
            continue
        valor = _parsear_numero(m.group("num"))
        if valor is None:
            continue
        if m.group("mil"):
            valor *= 1000
        montos.append(valor)
    for palabra, valor in _NUMEROS_PALABRA.items():
        if re.search(rf"\b{palabra}\b", t) and not re.search(rf"\d\s*{palabra}\b", t):
            montos.append(float(valor))
    return montos


def _reembolso_alto(texto_norm: str, texto: str) -> float | None:
    if not _INTENCION_REEMBOLSO.search(texto_norm):
        return None
    mayores = [m for m in extraer_montos(texto) if m > TOPE_REEMBOLSO]
    return max(mayores) if mayores else None


def evaluar(pregunta: str) -> list[Escalamiento]:
    """Devuelve las escalaciones que aplican (lista vacía si el agente puede responder)."""
    t = normalizar(pregunta)
    res: list[Escalamiento] = []
    if _LEGAL.search(t):
        res.append(Escalamiento(
            "tema_legal", "tema legal",
            f"Los temas legales los atiende una persona del equipo y no puedo resolverlos yo. "
            f"Escribí a {CONTACTO} y te van a ayudar."))
    if _TRATO.search(t):
        res.append(Escalamiento(
            "queja_trato", "queja sobre el trato de un empleado",
            f"Lamento que hayas tenido esa experiencia. Las quejas sobre el trato de un empleado las gestiona "
            f"una persona y no puedo resolverlas yo. Escribí a {CONTACTO}."))
    if _FACTURACION.search(t):
        res.append(Escalamiento(
            "disputa_facturacion", "disputa de facturación",
            f"Las disputas de facturación las resuelve una persona del equipo y no puedo gestionarlas yo. "
            f"Escribí a {CONTACTO} con los datos de la factura o el cobro."))
    monto = _reembolso_alto(t, pregunta)
    if monto is not None:
        res.append(Escalamiento(
            "reembolso_mayor_500", f"reembolso de ${monto:,.2f} (mayor a ${TOPE_REEMBOLSO:,.0f})",
            f"Los reembolsos mayores a ${TOPE_REEMBOLSO:,.0f} requieren la aprobación de un supervisor humano y no "
            f"puedo aprobarlos. Escribí a {CONTACTO} para que lo revisen."))
    return res


# --- Inyección de prompts en la entrada -----------------------------------------------------------------

_SENALES_INYECCION = [
    r"ignor\w* (?:todas? )?(?:las |tus )?(?:instrucciones|indicaciones|reglas)",
    r"olvid\w* (?:todas? )?(?:las |tus )?(?:instrucciones|indicaciones|reglas)",
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|rules)",
    r"disregard (?:the )?(?:previous|above|system)",
    r"(?:revel\w*|mostr\w*|imprim\w*|reveal|show|print) (?:el |tu |your |the )?(?:system prompt|prompt del sistema|"
    r"instrucciones del sistema|prompt)",
    r"a partir de ahora (?:sos|eres|actua|actuas)",
    r"you are now",
    r"modo (?:desarrollador|dios|sin restricciones)|developer mode|do anything now",
    r"aprob\w+ (?:el |mi )?reembolso (?:igual|de todos modos|sin)",
]
_RE_INYECCION = [re.compile(p) for p in _SENALES_INYECCION]


def detectar_inyeccion(texto: str) -> bool:
    t = normalizar(texto)
    return any(p.search(t) for p in _RE_INYECCION)
