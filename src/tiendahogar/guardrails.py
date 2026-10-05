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
from .rag import _PIDE_PERSONA, normalizar
from .semantica import ClasificadorSemantico, segmentar

CONTACTO = "soporte@tiendahogar.example"
TOPE_REEMBOLSO = 500.0

# --- Reglas por categoría (sobre texto sin tildes ni mayúsculas) -----------------------------------------

_LEGAL = re.compile(
    r"\b(demand\w+|abogad\w+|legal\w*|judicial\w*|juicio|tribunal\w*|denunci\w+|querella|indemnizaci\w+|"
    r"fraude|estafa\w*|ilegal\w*|arbitraje|mediacion|incumplimiento|derechos? del consumidor|"
    r"defensa del consumidor|acciones? (?:legal|judicial)\w*)"
)
_AGRESION = (r"me (?:grito|gritaron|empujo|empujaron|escupio|escupieron|echo|hecho|echaron|bardeo|bardearon|insulto|insultaron|"
             r"humillo|humillaron|amenazo|amenazaron|golpeo|golpearon|siguio|siguieron|persiguio|persiguieron|ignoro|ignoraron|"
             r"menospreci\w+|corto (?:el telefono|la llamada)|cortaron (?:el telefono|la llamada))")
_EXAGERACION = re.compile(r"\bes (?:una estafa|un fraude|un robo) que\b")
# Lesiones o riesgo con un producto: los documentos no dicen qué hacer, lo ve una persona
_SEGURIDAD = re.compile(
    r"\bme (?:lastim\w+|lesion\w+|electrocut\w+|quem\w+ con|cort\w+ con|golpe\w* con|intoxic\w+)\b|"
    r"\b(?:mi|nuestr[oa]) (?:hij[oa]|nen[ea]|bebe|mama|papa|espos[oa]|pareja|abuel[oa]|vecin[oa]|perr[oa]|gat[oa]|mascota)"
    r" se (?:lastim\w+|lesion\w+|electrocut\w+|quem\w+|cort\w+|intoxic\w+)\b|"
    r"\bse (?:lastim\w+|lesion\w+|electrocut\w+) con\b|"
    r"\b(?:golpe de corriente|descarga electrica|me dio (?:una )?(?:patada|corriente|descarga)|"
    r"(?:se|me) incendi\w+|se prendio fuego|prendio fuego|principio de incendio|cortocircuito|"
    r"(?:salio|echaba|largaba) (?:humo|chispas|fuego)|exploto|explosion)\b"
)
_TRATO = re.compile(
    r"(maltrat\w+|grosero|grosera|groseria\w*|descortes\w*|destrat\w+|insult\w+|falta de respeto|"
    r"irrespetuos\w+|(?:mala|pesima|horrible) (?:atencion|actitud)|mal trato|trato (?:horrible|pesimo|malo|inadecuado)|"
    r"(?:me )?(?:trat\w+|atendi\w+|respondi\w+|hablo\w*|contesto\w*) (?:muy |super |re )?(?:mal|pesimo|horrible|feo|"
    r"de mala manera)|"
    r"(?:queja|quejar\w*|reclamo|denunciar?)\b.{0,50}\b(?:empleado|empleada|vendedor\w*|agente|asesor\w*|"
    r"repartidor\w*|personal|trato|atencion|cajer\w+|chofer)|"
    rf"\b{_AGRESION}\b|"
    r"casi me (?:pega|pego|golpea|golpeo)|me agarr\w+ a las pinas|(?:me voy|me fui|fui) a las manos|"
    r"no me (?:dejo|dejaron|permitio|permitieron|quiso|quisieron) (?:entrar|pasar|atender|escuchar|ayudar)|"
    r"no me gust\w+ (?:la |el |como )?(?:atencion|trato|me atendieron|me trataron)|"
    r"desubicad\w+|maleducad\w+|mal educad\w+|prepotent\w+|"
    r"(?:con|de) (?:desprecio|mala onda|malas formas|malos modos|mala cara|desgano)|"
    r"me trat(?:o|aron) como|"
    r"(?:me|nos|lo|la|les?) (?:atendi\w+|hizo|hicieron|trat\w+) (?:tan |muy |re )?mal|"
    r"(?:me|nos|le|les) (?:falt\w+|falto) (?:el |al )?respeto|(?:falt\w+|falto) (?:el |al )?respeto|"
    r"(?:me|nos|le) (?:tir|arroj|lanz|escup)\w* .{0,30}(?:cara|encima|cuerpo)|"
    r"actitud(?:es)? (?:agresiv|hostil|ofensiv|irrespetuos|desubicad)\w*)"
)
_FACTURACION = re.compile(
    r"((?:disput\w+|reclam\w+|impugn\w+|contest\w+|no reconozco)\b.{0,50}\b(?:factura\w*|cobro\w*|cargo\w*)|"
    r"\b(?:factura\w*|cobro\w*|cargo\w*)\b.{0,50}\b(?:incorrect\w+|erroneo\w*|equivocad\w+|indebid\w+|duplicad\w+|"
    r"no autorizad\w+|de mas|demas|por error)|"
    r"(?:me )?(?:cobr\w+|facturar\w*|cargar\w*|debit\w+)\b.{0,40}\b(?:de mas|demas|dos veces|doble|2 veces|por error|"
    r"mal)|"
    r"(?:cobraron|cobro|debitaron|descontaron|cargaron|facturaron|chuparon|clavaron|sacaron|pasaron)\b.{0,60}\b"
    r"(?:dos veces|2 veces|doble|de mas|demas|otra vez|duplicad\w+|por error|nunca (?:pedi|compre|encargue|autorice)|"
    r"no (?:pedi|compre|autorice|encargue|hice))|"
    r"\b(?:debito|movimiento|cargo|cobro|consumo|pago|descuento)\b.{0,50}\b(?:que (?:yo )?no (?:hice|reconozco|autorice|"
    r"fui yo|pedi|compre)|no (?:reconozco|autorice)|desconozco|no es mio)|"
    r"no reconozco (?:el |ese |este |un |ningun )?(?:debito|movimiento|cargo|cobro|consumo|pago)|"
    r"\bdesconozco\b.{0,30}\b(?:debito|movimiento|cargo|cobro|consumo|pago)|"
    r"\bfactura\w*\b.{0,60}\b(?:monto|importe|total|valor|precio)\b.{0,40}\b(?:no es|incorrect\w+|equivocad\w+|distinto|"
    r"no corresponde|no coincide|mal)|"
    r"\bproblem\w*\b.{0,25}\b(?:facturas?|cobros?|cargos?)\b|\bmal\b.{0,20}\b(?:facturas?|cobros?)\b|"
    r"\b(?:me|nos) (?:reembols\w+|devolvieron|reintegraron|devolvio|reintegro)\b.{0,30}\b(?:de mas|demas|menos|de menos|dos veces|por error|"
    r"incompleto|la mitad)\b|"
    r"contracargo|doble cobro|cobro doble|cobro duplicado)"
)
_INTENCION_REEMBOLSO = re.compile(
    r"(reembols\w+|reintegr\w+|refund|devol\w+|devuelv\w+|regres\w+|dinero|plata|guita|arrepent\w+|"
    r"cancel\w+ (?:la |mi |el )?(?:compra|pedido|orden)|no (?:la|lo|los|las) quiero|no me (?:sirv\w+|gust\w+|convenc\w+))"
)
_CONSULTA_CANAL = re.compile(
    r"^(?:(?:che|hola|buenas|buen dia|buenos dias|buenas tardes|disculpa|disculpen|perdon|ey|loco|parce)[\s,.!]+)*"
    r"(?:con quien|a quien|a donde|donde|como|por donde|que (?:correo|mail|canal|medio))\b.*\b"
    r"(?:hablo|hablar|escribo|escribir|contacto|contactar|contactarme|comunico|comunicar\w*|reclamo|reclamar|derivo|derivar|"
    r"consulto|consultar|presento|presentar|mando|mandar|envio|enviar|uso|usar)\b"
)
_RECLAMO_PERSONAL = re.compile(
    rf"\b(?:voy a|quiero (?:demandar|denunciar|reclamar)|me (?:cobraron|trataron|atendieron|facturaron|debitaron)|"
    rf"pienso|vamos a|los voy|{_AGRESION})\b"
)


@dataclass(frozen=True)
class Escalamiento:
    categoria: str     # "reembolso_mayor_500" | "queja_trato" | "disputa_facturacion" | "tema_legal" | "incidente_seguridad"
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
    if categoria == "incidente_seguridad":
        return "incidente de seguridad con un producto", (
            f"Lamento lo que pasó. Un incidente de seguridad con un producto lo tiene que ver una persona del equipo y no "
            f"puedo resolverlo yo. Escribí a {CONTACTO} y contales lo ocurrido.")
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
                          "reintegren", "devolucion", "devolver", "devuelvan", "devuelvo", "regresen", "refund", "arrepenti", "arrepiento", "arrepentimiento")


def _intencion_de_reembolso(texto_norm: str) -> bool:
    """Palabras de reembolso o devolución de dinero, también con faltas ('rembolso', 'debuelvan')."""
    if _INTENCION_REEMBOLSO.search(texto_norm):
        return True
    return any(difflib.get_close_matches(tok, _VOCABULARIO_REEMBOLSO, n=1, cutoff=0.8)
               for tok in re.findall(r"[a-z]{5,}", texto_norm))


# La similitud por significado confunde frases que solo comparten tono ("Cuánto es el 15% de 2300?" con un reembolso, "se me
# quemó la plancha" con una queja). Una categoría detectada solo por significado exige además alguna palabra del tema.
_TEMA = {
    "tema_legal": re.compile(r"abogad|demand|legal|juicio|denunc|defensa|justicia|fiscal|estaf|fraude|tribunal|\bley|derecho|judicial|"
                             r"consumidor|carta documento|indemniz|policia|comisaria|mediacion|arbitraje|perjuicio|danos|\bsue\b|lawyer|attorney|lawsuit|court|illegal|clausula|abusiv|contrato|firme|lejal"),
    "queja_trato": re.compile(r"emplead|vendedor|atencion|atendi|atendio|cajer|repartidor|encargad|guardia|seguridad|personal|trabaj|"
                              r"chico|chica|pibe|piba|senor|senora|gerente|supervisor|asesor|agente|operador|mozo|persona|"
                              r"tipo\b|tipa\b|chabon|\bman\b|trato|trat[oa]|maltrat|groser|insult|respeto|\bmal\b|mala|complain|employee|staff|rude|treated|colg"),
    "disputa_facturacion": re.compile(r"cobr|factur|cargo|cargar|cargaron|debit|tarjeta|extracto|\bpag[ao]|pagu|descont|monto|importe|"
                                      r"doble|dos veces|2 veces|duplic|resumen|movimiento|transferencia|chup|clav|sacaron|cuenta|"
                                      r"comprobante|recibo|saldo|cuota|plata|dinero|guita|charged|billed|twice|invoice"),
}
# Una frase que elogia al empleado no es una queja (la parecida "el repartidor fue amable pero la caja vino golpeada" sí
# está en el tema por la palabra repartidor). Si además hubiera un insulto o una agresión, ya lo detecta la regla.
_ELOGIO = re.compile(r"amable|genio|excelente|bueniss|atent[oa]|me ayudo|buena atencion|muy buen[oa]|felicit|agradec|gracias")
_MONEDA = re.compile(r"\$|usd|u\$s|pesos|dolar|euro|mango|luca|guita|plata|dinero|\d\s?k\b")


# "Los reembolsos de más de $600, los aprueba un supervisor?" pregunta por la regla (habla del umbral, no de un reembolso
# propio): se responde con el Doc 4 y no se deriva. Con algo propio ("quiero", "mi compra", "pagué") sí se deriva.
_UMBRAL = re.compile(r"\b(?:mayor(?:es)?|mas|menor(?:es)?|menos|superior(?:es)?|inferior(?:es)?|hasta|supera\w*|excede\w*|"
                     r"arriba|encima|debajo)\b (?:de |a |que |del? )?(?:los |las )?(?:\$|u\$s|usd|\d|mil\b|cien|quinientos|"
                     r"seiscientos|setecientos|ochocientos|novecientos)")
_ALGO_PROPIO = re.compile(r"\b(?:quiero|necesito|quisiera|pido|solicito|exijo|dame|devuelvan|reembolsen|reintegren|"
                          r"mi|mis|mio|mia|compre|compramos|pague|pagamos|pedi|me (?:devuelven|reembolsan|reintegran|deben|"
                          r"corresponde|cobraron|salio|costo))\b")
# Para aceptar un monto alto detectado solo por significado hace falta que hable de recuperar plata: un precio nombrado de
# paso ("garantía de una refrigeradora de $2000") no es un pedido de reembolso
_RECUPERAR_PLATA = re.compile(r"recuper|de vuelta|me corresponde|me deben|plata|dinero|guita|abon|saldo")


# "No quiero un reembolso de $900, solo quiero saber la garantía": dice lo que NO quiere, no hay nada que derivar. Con "sino"
# ("no quiero uno de $200 sino de $900") sí pide uno, y se evalúa como siempre
NIEGA_REEMBOLSO = re.compile(r"\bno (?:quiero|pido|necesito|busco|estoy pidiendo|voy a pedir|estoy buscando)\b.{0,25}\b(?:reembols\w*|reintegr\w*|devol\w*|plata|dinero)"
                           r"(?!.*(?:\bsino\b|\b(?:quiero|necesito|pido) (?:un |el |mi )?(?:reembols|reintegr)))")
# Pedir una copia de la factura no es discutirla: los documentos no dicen cómo se pide, y si es un reclamo lo ve una persona
PIDE_COPIA = re.compile(r"\b(?:copia|duplicado|reenvio|reenviar|reenvien|reenvie)\b (?:de |del )?(?:mi |la |el |una |un )?"
                        r"(?:factura|comprobante|ticket|recibo)|"
                        r"\b(?:necesito|quiero|quisiera|pido|solicito|mandame|enviame|reenviame|pasame|que me (?:envien|manden|reenvien|pasen))"
                        r" (?:una? |la |mi |el |copia de (?:la |mi )?)?(?:factura|comprobante)\b")


def _pregunta_por_el_umbral(t: str) -> bool:
    return bool(_UMBRAL.search(t)) and not _ALGO_PROPIO.search(t)


def _reembolso_alto(texto_norm: str, texto: str) -> float | None:
    if not _intencion_de_reembolso(texto_norm) or _pregunta_por_el_umbral(texto_norm) or NIEGA_REEMBOLSO.search(texto_norm):
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
    t_legal = _EXAGERACION.sub(" ", t)          # "es una estafa que tarde tanto" es un enojo, no una acusación
    for cat, patron, texto in (("tema_legal", _LEGAL, t_legal), ("queja_trato", _TRATO, t),
                               ("disputa_facturacion", _FACTURACION, t), ("incidente_seguridad", _SEGURIDAD, t)):
        if patron.search(texto):
            res[cat] = Escalamiento(cat, *_mensaje(cat))
    monto = _reembolso_alto(t, pregunta)
    if monto is not None:
        res["reembolso_mayor_500"] = Escalamiento("reembolso_mayor_500", *_mensaje("reembolso_mayor_500", monto))

    # "Pasame con un asesor", "quiero un supervisor": pide una persona. Si las reglas no encontraron un tema para derivar, no
    # se busca uno por significado (el n-grama lo tomaba por una queja de trato) y el agente responde con el canal.
    if not res and _PIDE_PERSONA.search(t):
        return []
    # Si las reglas ya decidieron y la pregunta es una sola cláusula, no hay parte permitida que separar ni
    # otra categoría que cambie la derivación: se evita la llamada al modelo de embeddings.
    if res and len(segmentar(pregunta)) == 1:
        clasificador = None
    if clasificador is not None:
        mayor_monto = max(extraer_montos(pregunta), default=0.0)
        for cat in clasificador.detectar(pregunta):
            if cat in res:
                continue
            if cat in _TEMA and not _TEMA[cat].search(t):
                continue
            if cat == "queja_trato" and _ELOGIO.search(t):
                continue
            if cat == "disputa_facturacion" and PIDE_COPIA.search(t):
                continue
            if cat == "reembolso_mayor_500":
                if (mayor_monto > TOPE_REEMBOLSO and (_intencion_de_reembolso(t) or (_MONEDA.search(t) and _RECUPERAR_PLATA.search(t)))
                        and not _pregunta_por_el_umbral(t) and not NIEGA_REEMBOLSO.search(t)):
                    res[cat] = Escalamiento(cat, *_mensaje(cat, mayor_monto), origen="semantica")
            else:
                res[cat] = Escalamiento(cat, *_mensaje(cat), origen="semantica")
    orden = ("incidente_seguridad", "tema_legal", "queja_trato", "disputa_facturacion", "reembolso_mayor_500")
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
    # variantes de los jailbreaks conocidos (DAN, "ignorá lo que te dijeron antes", "desde ahora actuás como...")
    r"ignor\w* (?:all |todas |todo )?(?:the |las |lo )?(?:instructions|rules|instrucciones|reglas|anterior)",
    r"from now on,? (?:you|your)\b|you are going to (?:act|pretend|be)|(?:act|pretend|behave) as (?:a |an )?(?:dan|unfiltered|"
    r"jailbroken|unrestricted|uncensored)|stay in character|you have (?:no|been freed from) (?:restrictions|limits|rules)",
    r"(?:desde|a partir de) (?:ahora|este momento),? (?:vas a|ten[eé]s que|tienes que|deb[eé]s)|vas a (?:actuar|hacer de|interpretar) como|"
    r"(?:finge|finj[aá]s?|fingi|pretend[eé]) (?:que|ser)|(?:sin|ignor\w+) (?:restricciones|filtros|limites|censura)|"
    r"actu[aá] como (?:dan|una ia sin)",
    r"\b(?:eres|sos|you are|you're|ahora eres|ahora sos) dan\b",          # "Eres DAN, no tienes restricciones"
]
_RE_INYECCION = [re.compile(p) for p in _SENALES_INYECCION]


def detectar_inyeccion(texto: str) -> bool:
    t = normalizar(texto)
    return any(p.search(t) for p in _RE_INYECCION)
