"""Qué quiere el cliente, leído con reglas sobre el texto sin tildes: pedir plata, devolver, cancelar un pedido, hablar de
envíos, dar su compra por hecha. Son patrones simples; lo que decide qué se responde está en agent.py."""

import re

from . import guardrails
from .sesion import TIEMPO

COMPRA_FUTURA = re.compile(
    r"\b(voy a (hacer|comprar|realizar|pedir|encargar)|quiero (hacer|realizar) una (compra|pedido)|quisiera (hacer|comprar)|"
    r"si (compro|pido|encargo|hago (la|una) compra)|antes de comprar|pienso comprar|estoy por comprar|"
    r"queria comprar|quiero comprar|me gustaria comprar|para comprar)\b")
COMPRA_PROPIA = re.compile(
    r"\b(mi|mis|mio|mia|nuestro|nuestra|pedi|pedimos|compre|compramos|encargue|hice|hicimos|realice|adquiri|"
    r"me (?:llego|falta|entregaron|mandaron|despacharon))\b")
PIDE_PLATA = re.compile(r"reembols|reintegr|\bplata\b|dinero|guita|\b(?:me )?devuelv\w+(?:me)? (?:la|el|mi|los|las)\b")
PEDIDO_PERSONAL = re.compile(r"\b(?:quiero|quisiera|necesito|pido|solicito|exijo)\b|\bme (?:devuelven|reembolsan|reintegran)\b(?![^?]*[?])|"
                              r"\b(?:devuelvan|reembolsen|reintegren)\b")
PREGUNTA_DE_POLITICA = re.compile(r"cuanto|cuando|como|quien|plazo|tarda|demora|politica|condicion|requisito|aprueba|"
                                   r"aprobacion|donde|que pasa|metodo|efectivo|tarjeta|transferencia|debito|credito")
PRODUCTOS = ("refrigeradora", "heladera", "nevera", "lavadora", "estufa", "licuadora", "plancha", "tostadora")


OBJETO_DE_COMPRA = re.compile(r"\b(?:pedidos?|compras?|adquisicion(?:es)?|compre|ordenes|orden|encargos?|envios?|paquetes?|entregas?|productos?|"
                               r"electrodomesticos?|heladeras?|refrigeradoras?|lavadoras?|estufas?|licuadoras?|planchas?|tostadoras?)\b")
TAREA_AJENA = re.compile(r"\b(?:escrib|cont[ae]|cuent|decime|dime|dame|armame|haceme|traduc|traduz|resum|explic|cant[ae]|dibuj|invent|"
                          r"recomend|ayudame|program|calcul|resolv|imagin|pretend|actu[ae]|jug[aá]|simul)\w*|"
                          r"\b(?:respond|habl|conte?st)\w* (?:en|como|con|solo)\b|\b(?:poema|cuento|chiste|receta|rima|cancion)\b")
PIDE_COPIA = guardrails.PIDE_COPIA
SIN_COMPROBANTE = re.compile(r"no (?:me )?(?:dieron|dio|entregaron|entrego|enviaron|mandaron|emitieron|hicieron|llego|llegaron)"
                              r" (?:la |el |una |un )?(?:factura|comprobante|ticket|recibo)|"
                              r"no (?:recibi|recibimos|tengo) (?:la |el |una |un |ninguna? )?(?:factura|comprobante|ticket|recibo)|"
                              r"sin (?:la |el |una |un )?(?:factura|comprobante)")
NO_DEVOLVIBLE = re.compile(r"liquidacion|personalizad|oferta final|a medida|a pedido|"
                            r"(?:hech[oa]s?|hicieron|fabricaron|fabricad[oa]|disenaron|armaron) (?:solo |especialmente |exclusivamente )?"
                            r"(?:para mi|a pedido)")
ACCION_QUE_NO_PUEDE = re.compile(
    r"reserv\w+|apart\w+ (?:un|una|el|la)|compr\w+ por mi|(?:hace|hag\w+) (?:la |una |mi )?(?:compra|reserva) por mi|agend\w+|"
    r"program\w+ (?:una |la |mi )?(?:entrega|llamada|visita)|llam\w*me|"
    r"\b(?:envi|mand)(?:a|e|es|ar|ame|arme)\b (?:me )?(?:un |el |la |una |mi )?(?:correo|mail|email|resumen|factura|comprobante|mensaje|sms)|"
    r"\b(?:gener|emit|hag|hac)\w* (?:me )?(?:una |la |mi |un )?(?:factura|comprobante)|"
    r"(?:quiero|quisiera|puedo|podria|necesito|voy a) cancel\w+|cancel(?:ar|o|e)(?:lo|la|me)\b|"
    r"cancel\w+ (?:el |mi |la |este |ese )?(?:pedido|orden|compra)|anul\w+ (?:el |mi |la )?(?:pedido|orden|compra)|"
    r"actualiz\w+ (?:el )?estado|modific\w+ (?:mi |el |la )?(?:pedido|direccion|compra)|cambi\w+ (?:la |mi )?direccion|"
    r"avis\w+ (?:a|al) (?:la |el )?(?:empresa|transportista|correo)")
HABLA_DE_PLATA = re.compile(r"reembols|reintegr|plata|dinero|guita|pago|pague|cobr|tarjeta|efectivo|monto|importe|\$|usd|pesos|dolar")
QUIERE_DEVOLVER = re.compile(r"devol|devuelv")
INTERNACIONAL = re.compile(r"\b(?:internacional\w*|exterior|otro pais|otros paises|afuera del pais|fuera del pais|al extranjero)\b")
ENVIO_EXPLICITO = re.compile(r"\b(?:envi\w*|entreg\w*|despach\w*|paquete\w*|flete|domicilio|repart\w*)\b")
NOMBRA_EL_DOCUMENTO = {"garantia": re.compile("garant"), "devoluciones": re.compile("devol|devuelv"),
                        "reembolsos": re.compile("reembols|reintegr"), "envios": re.compile("envi|entreg|despach"),
                        "contacto": re.compile("contact|soporte|mail|correo")}
PIDE_COSTO = re.compile(r"cuesta|costo|precio|tarifa|cobran|gratis|cuanto sale|cuanto vale|cuanto se paga|pagar")
INTENCION_ENVIO = re.compile(r"envi|entreg|llega|despach|manda|demora|tarda|recib|flete|domicilio|reparto|repart")
TEMA_DE_POLITICA = re.compile(r"devol|garantia|reembols|cambiar|rompi|descompus|defect|\bfall")
TEMA_DE_ESTADO = re.compile(r"estado|donde (?:esta|anda|viene)|rastre|seguimiento|llega|demora|cuando (?:llega|viene|sale)|despach")
SU_COMPRA = re.compile(r"\b(?:mi|mis|compre|compramos|hice|pedi)\b|"
                        r"\b(?:quiero|quisiera|necesito|puedo|podria|me gustaria) (?:hacer|iniciar|gestionar|tramitar|pedir|solicitar) "
                        r"(?:una |la |mi )?(?:devolucion|cambio)\b|"
                        r"\b(?:quiero|quisiera|necesito|puedo|podria|se puede) (?:devolver|cambiar|reparar|arreglar)\b|"
                        r"\b(?:la|lo|las|los) (?:puedo|podria|se puede) (?:devolver|cambiar)\b|\bse me\b|"
                        r"\bme (?:la|lo|las|los) (?:cubre|cubren|aceptan|cambian|reparan|devuelven)\b")
# un producto que no se devuelve en ningún caso, o que el cliente dice por qué falló (puede decidir otra regla)
NO_SE_DEVUELVE = re.compile(NO_DEVOLVIBLE.pattern + r"|\bporque\b|mal uso|se me cayo|golpe|\bmoj[eo]\b|\busad[oa]s?\b|ya (?:la |lo |las |los )?use\b")


def pregunta_por_su_compra(pregunta: str, fuentes: list[str]) -> bool:
    """¿Pregunta por la devolución o la garantía de algo suyo sin decir cuándo lo compró? Solo entonces conviene
    preguntar la antigüedad: una pregunta de política ("cuánto dura la garantía?"), una compra futura, un producto en
    liquidación o personalizado (no se devuelve en ningún caso) o una que ya trae el tiempo no la necesitan."""
    p = guardrails.normalizar(pregunta)
    return bool(fuentes and set(fuentes) <= {"devoluciones", "garantia"} and SU_COMPRA.search(p)
                and not PREGUNTA_DE_POLITICA.search(p) and not TIEMPO.search(p) and not COMPRA_FUTURA.search(p)
                and not NO_SE_DEVUELVE.search(p) and not PIDE_PLATA.search(p))


def dice_sin_comprobante(pregunta: str) -> bool:
    p = guardrails.normalizar(pregunta)
    return bool(SIN_COMPROBANTE.search(p) or PIDE_COPIA.search(p))


def pide_reembolso(pregunta: str) -> bool:
    """¿Pide que le devuelvan plata (y no pregunta por la política de reembolsos)?"""
    p = guardrails.normalizar(pregunta)
    return bool(PIDE_PLATA.search(p) and PEDIDO_PERSONAL.search(p) and not PREGUNTA_DE_POLITICA.search(p)
                and not guardrails.NIEGA_REEMBOLSO.search(p))
