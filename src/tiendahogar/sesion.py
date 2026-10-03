"""Memoria de una conversación: qué dato le falta al agente y qué le preguntó al cliente.

No guarda el historial de mensajes sino un estado chico y estructurado (el patrón de "slot filling" de los chatbots de
tareas): qué dato está pendiente (el lugar, el monto o el número de pedido), la consulta que quedó incompleta y cuántas
veces se repreguntó. El mensaje siguiente se lee como respuesta a esa pregunta con los mismos extractores que ya usa el
agente (`lugares`, `montos`, `pedidos`); si calza, se arma la consulta completa y pasa por el pipeline de siempre,
guardrail incluido, así que la memoria no abre ningún atajo.

La memoria es opcional y la maneja quien llama: `agente.responder(pregunta)` sin sesión no recuerda nada (cada pregunta es
independiente, también si se reutiliza el agente), y `agente.responder(pregunta, sesion)` sí. Límites de la prueba:
el dato pendiente se olvida a los `MAX_TURNOS` mensajes y se repregunta como máximo `MAX_REPREGUNTAS` veces por dato.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import guardrails
from .lugares import PREGUNTA_LUGAR, Lugar, resolver_lugares
from .montos import extraer_montos
from .pedidos import extraer_identificadores_raros, extraer_referencias
from .rag import normalizar

MAX_TURNOS = 5
MAX_REPREGUNTAS = 2

PREGUNTA_MONTO = (f"¿De cuánto fue la compra? Con ese dato te confirmo si hace falta la aprobación de un supervisor "
                  f"(se necesita por encima de ${guardrails.TOPE_REEMBOLSO:,.0f}).")
PREGUNTA_PEDIDO = "Necesito el número de pedido (formato ORD-XXXX) para consultarlo."
SIN_PEDIDO = ("Sin el número de pedido (formato ORD-XXXX) no puedo consultar su estado. Cuando lo tengas, escribilo y "
              "lo reviso.")

_SI = re.compile(r"^(?:si|sii+|claro|asi es|correcto|exacto|exactamente|dale|aja|ajam|afirmativo|efectivamente|yes)\b")
_NO = re.compile(r"^(?:no|nop|nope|negativo|para nada)\b(?! (?:se|lo se|recuerdo|me acuerdo|tengo|sabria))")
_NO_SE = re.compile(r"\bno (?:se|lo se|recuerdo|me acuerdo|tengo idea|sabria)\b|ni idea|\bno (?:lo )?tengo\b")
_DEFINIDOS = {"capital", "otra", "exterior"}


@dataclass
class Sesion:
    pendiente: str | None = None        # "lugar" | "lugar_confirmar" | "monto" | "pedido"
    base: str = ""                      # la consulta que quedó incompleta
    si: Lugar | None = None             # con un "sí" a la pregunta de confirmar, el lugar es este
    no: Lugar | None = None             # con un "no": este (si es None, se pregunta el lugar de nuevo)
    repreguntas: int = 0
    turnos: int = 0                     # mensajes desde que quedó pendiente

    def esperar(self, pendiente: str, base: str, si: Lugar | None = None, no: Lugar | None = None) -> None:
        if self.pendiente != pendiente or self.base != base:
            self.repreguntas = 0
        self.pendiente, self.base, self.si, self.no, self.turnos = pendiente, base, si, no, 0

    def limpiar(self) -> None:
        self.pendiente, self.base, self.si, self.no = None, "", None, None
        self.repreguntas = self.turnos = 0


@dataclass(frozen=True)
class Turno:
    """Qué hacer con el mensaje: responder `repregunta` tal cual, o responder `consulta` (ya completa)."""
    consulta: str = ""
    lugar: Lugar | None = None          # lugar ya confirmado por el cliente con un sí o un no
    repregunta: str | None = None
    repreguntar: bool = True            # False: no vuelvas a preguntar este dato (se superó el máximo)


def _es_un_intento(mensaje: str) -> bool:
    """Un mensaje corto y sin pregunta parece una respuesta (aunque no sirva); uno largo o con pregunta, un tema nuevo."""
    return len(mensaje.split()) <= 6 and "?" not in mensaje


def _reintentar(sesion: Sesion, pregunta: str, final: Turno) -> Turno:
    if sesion.repreguntas >= MAX_REPREGUNTAS:
        sesion.limpiar()
        return final
    sesion.repreguntas += 1
    return Turno(repregunta=pregunta)


def interpretar(sesion: Sesion, mensaje: str) -> Turno | None:
    """Lee `mensaje` como respuesta al dato pendiente. None: no hay nada pendiente o es un tema nuevo."""
    if not sesion.pendiente:
        return None
    sesion.turnos += 1
    if sesion.turnos > MAX_TURNOS:
        sesion.limpiar()
        return None
    t = normalizar(mensaje).strip(" ¿?¡!.,")
    base, pendiente = sesion.base, sesion.pendiente

    if pendiente == "lugar_confirmar":
        if _SI.match(t) and sesion.si:
            lugar = sesion.si
            sesion.limpiar()
            return Turno(base, lugar=lugar)
        if _NO.match(t):
            if sesion.no:
                lugar = sesion.no
                sesion.limpiar()
                return Turno(base, lugar=lugar)
            sesion.pendiente = "lugar"          # dijo que no: ahora sí hay que preguntarle dónde está
            return Turno(repregunta=PREGUNTA_LUGAR)
        pendiente = "lugar"                     # contestó con un lugar en vez de sí o no

    if pendiente == "lugar":
        if any(l.tipo in _DEFINIDOS for l in resolver_lugares(mensaje)):
            sesion.limpiar()
            return Turno(f"{base} {mensaje}")
        if _es_un_intento(mensaje):
            return _reintentar(sesion, PREGUNTA_LUGAR, Turno(base, repreguntar=False))
    elif pendiente == "monto":
        if extraer_montos(mensaje):
            sesion.limpiar()
            return Turno(f"{base} {mensaje}")
        if _NO_SE.search(t):                    # no sabe el monto: se responde la política sin volver a preguntar
            sesion.limpiar()
            return Turno(base, repreguntar=False)
        if _es_un_intento(mensaje):
            return _reintentar(sesion, PREGUNTA_MONTO, Turno(base, repreguntar=False))
    elif pendiente == "pedido":
        if extraer_referencias(mensaje) or extraer_identificadores_raros(mensaje):
            sesion.limpiar()
            return Turno(f"{base} {mensaje}")
        numero = re.fullmatch(r"(?:el |la |lo |mi |es |ese |esa )*(?:pedido |orden |nro\.? |numero |n[°º] |# )?(\d{3,8})", t)
        if numero:
            sesion.limpiar()
            return Turno(f"{base} pedido {numero.group(1)}")
        if _es_un_intento(mensaje):
            return _reintentar(sesion, PREGUNTA_PEDIDO, Turno(repregunta=SIN_PEDIDO))
    sesion.limpiar()                            # otro tema: se descarta lo pendiente y se responde el mensaje solo
    return None
