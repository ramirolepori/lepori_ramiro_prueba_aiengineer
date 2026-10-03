"""Guardrails determinísticos: corren ANTES del modelo, así que no dependen de que el LLM obedezca.

Casos que el agente no resuelve (Doc 4 y Doc 5): reembolsos mayores a $500, quejas sobre el trato de un
empleado, disputas de facturación y temas legales. Se escalan a soporte@tiendahogar.example.
Reembolso de exactamente $500 NO escala: el documento dice "mayores a $500".
Además hay una detección simple de intentos de inyección de prompt en la entrada.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .montos import extraer_montos
from .rag import normalizar
from .semantica import ClasificadorSemantico, segmentar

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
_CONSULTA_CANAL = re.compile(
    r"^(?:con quien|a quien|a donde|donde|como|por donde|que (?:correo|mail|canal|medio))\b.*\b"
    r"(?:hablo|escribo|contacto|comunico|reclamo|derivo|consulto|presento|mando|envio)\b"
)
_RECLAMO_PERSONAL = re.compile(
    r"\b(?:voy a|quiero (?:demandar|denunciar|reclamar)|me (?:cobraron|trataron|atendieron|facturaron|debitaron)|"
    r"pienso|vamos a|los voy)\b"
)


@dataclass(frozen=True)
class Escalamiento:
    categoria: str     # "reembolso_mayor_500" | "queja_trato" | "disputa_facturacion" | "tema_legal"
    motivo: str
    mensaje: str       # lo que se le responde al cliente
    origen: str = "regla"   # "regla" o "semantica"


def _es_consulta_de_canal(texto_norm: str) -> bool:
    """'Con quién hablo si tengo un tema legal?' pregunta por el canal: se responde con el Doc 5, no se deriva
    a ciegas. Una frase con un reclamo propio ('voy a demandar, con quién hablo?') sí se deriva."""
    return bool(_CONSULTA_CANAL.search(texto_norm.strip(" ¿?¡!"))) and not _RECLAMO_PERSONAL.search(texto_norm)


def _mensaje(categoria: str, monto: float | None = None) -> tuple[str, str]:
    """(motivo, mensaje al cliente) de cada categoría."""
    if categoria == "tema_legal":
        return "tema legal", (f"Los temas legales los atiende una persona del equipo y no puedo resolverlos yo. "
                              f"Escribí a {CONTACTO} y te van a ayudar.")
    if categoria == "queja_trato":
        return "queja sobre el trato de un empleado", (
            f"Lamento que hayas tenido esa experiencia. Las quejas sobre el trato de un empleado las gestiona "
            f"una persona y no puedo resolverlas yo. Escribí a {CONTACTO}.")
    if categoria == "disputa_facturacion":
        return "disputa de facturación", (
            f"Las disputas de facturación las resuelve una persona del equipo y no puedo gestionarlas yo. "
            f"Escribí a {CONTACTO} con los datos de la factura o el cobro.")
    return f"reembolso de ${monto:,.2f} (mayor a ${TOPE_REEMBOLSO:,.0f})", (
        f"Los reembolsos mayores a ${TOPE_REEMBOLSO:,.0f} requieren la aprobación de un supervisor humano y no "
        f"puedo aprobarlos. Escribí a {CONTACTO} para que lo revisen.")


_VOCABULARIO_REEMBOLSO = ("reembolso", "reembolsar", "reembolsen", "reembolsan", "reintegro", "reintegrar",
                          "reintegren", "devolucion", "devolver", "devuelvan", "devuelvo", "regresen", "refund")


def _intencion_de_reembolso(texto_norm: str) -> bool:
    """Palabras de reembolso o devolución de dinero, también con faltas ('rembolso', 'debuelvan')."""
    if _INTENCION_REEMBOLSO.search(texto_norm):
        return True
    return any(difflib.get_close_matches(tok, _VOCABULARIO_REEMBOLSO, n=1, cutoff=0.8)
               for tok in re.findall(r"[a-z]{5,}", texto_norm))


def _reembolso_alto(texto_norm: str, texto: str) -> float | None:
    if not _intencion_de_reembolso(texto_norm):
        return None
    mayores = [m for m in extraer_montos(texto) if m > TOPE_REEMBOLSO]
    return max(mayores) if mayores else None


def evaluar(pregunta: str, clasificador: ClasificadorSemantico | None = None) -> list[Escalamiento]:
    """Devuelve las escalaciones que aplican (lista vacía si el agente puede responder).

    Primero las reglas. Con `clasificador`, se suman las categorías que reconoce por significado (paráfrasis,
    faltas de ortografía). El reembolso exige además un monto mayor a $500, que siempre lo extrae el parser.
    """
    t = normalizar(pregunta)
    if _es_consulta_de_canal(t):
        return []
    res: dict[str, Escalamiento] = {}
    for cat, patron in (("tema_legal", _LEGAL), ("queja_trato", _TRATO), ("disputa_facturacion", _FACTURACION)):
        if patron.search(t):
            res[cat] = Escalamiento(cat, *_mensaje(cat))
    monto = _reembolso_alto(t, pregunta)
    if monto is not None:
        res["reembolso_mayor_500"] = Escalamiento("reembolso_mayor_500", *_mensaje("reembolso_mayor_500", monto))

    # Si las reglas ya decidieron y la pregunta es una sola cláusula, no hay parte permitida que separar ni
    # otra categoría que cambie la derivación: se evita la llamada al modelo de embeddings.
    if res and len(segmentar(pregunta)) == 1:
        clasificador = None
    if clasificador is not None:
        mayor_monto = max(extraer_montos(pregunta), default=0.0)
        for cat in clasificador.detectar(pregunta):
            if cat in res:
                continue
            if cat == "reembolso_mayor_500":
                if mayor_monto > TOPE_REEMBOLSO:
                    res[cat] = Escalamiento(cat, *_mensaje(cat, mayor_monto), origen="semantica")
            else:
                res[cat] = Escalamiento(cat, *_mensaje(cat), origen="semantica")
    orden = ("tema_legal", "queja_trato", "disputa_facturacion", "reembolso_mayor_500")
    return [res[c] for c in orden if c in res]


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
