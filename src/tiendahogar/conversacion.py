"""Charla que no es una consulta: saludos, despedidas y agradecimientos. Se reconocen con reglas, sin modelo."""

import re

from . import guardrails

_AGRADECE = re.compile(r"agradec|gracias|felicit|conforme|satisfech|content[oa]|excelente|amabl|muy bien|todo bien|"
                       r"salio todo bien|genial|me encanto|me gusto")
_NO_ES_SOLO_AGRADECIMIENTO = re.compile(r"\?|devol|reembols|reclam|queja|problema|falla|\brot[oa]|no funciona|no (?:me )?(?:llego|dieron|gust)|"
                                        r"cuando|cuanto|como|donde|quiero|necesito|puedo|\bpero\b|\bmal\b|demor|tard")
_SALUDO = re.compile(r"(?:(?:hola|holi|holis|buenas|buen dia|buenos dias|buenas tardes|buenas noches|hey|ey|que tal|como estas|"
                     r"como andas|como va|todo bien|buen dia a todos|saludos)\s*)+|solo te salude|solo salude")
_DESPEDIDA = re.compile(r"(?:(?:chau|chao|adios|hasta luego|hasta pronto|nos vemos|hasta manana|bye|saludos|un saludo|"
                        r"buenas noches|que andes bien|nos hablamos|cuidate|gracias|muchas gracias)\s*)+")


def _solo_palabras(pregunta: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", guardrails.normalizar(pregunta))).strip()


def es_saludo(pregunta: str) -> bool:
    """Un mensaje que solo saluda: se saluda y se dice en qué se puede ayudar, no se responde "no tengo esa información"."""
    p = _solo_palabras(pregunta)
    if p.startswith("pero "):
        p = p[5:]
    p = re.sub(r"\b(?:me llamo|mi nombre es|soy)\s+[a-z]+(?: [a-z]+)?$", "", p).strip()   # "hola, me llamo Ramiro"
    palabras = p.split()
    repetida = bool(palabras) and max(palabras.count(w) for w in palabras) > 2     # "hola hola hola ..." es ruido
    return bool(palabras) and len(palabras) <= 6 and not repetida and _SALUDO.fullmatch(p) is not None


def es_despedida(pregunta: str) -> bool:
    p = _solo_palabras(pregunta)
    return bool(re.search(r"\b(?:chau|chao|adios|hasta luego|hasta pronto|nos vemos|bye|hasta manana)\b", p)
                and _DESPEDIDA.fullmatch(p + " "))


def es_agradecimiento(pregunta: str) -> bool:
    """Un mensaje que solo agradece o felicita (sin pregunta ni pedido): se agradece, no se responde con una política."""
    p = guardrails.normalizar(pregunta)
    return bool(_AGRADECE.search(p) and not _NO_ES_SOLO_AGRADECIMIENTO.search(p))