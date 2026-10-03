"""Preguntas mixtas: se responde la parte permitida y después se deriva lo que corresponde."""

import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.guardrails import CONTACTO


@pytest.fixture(scope="module")
def agente():
    return AgenteSoporte()


@pytest.mark.parametrize("pregunta,categoria,debe_contener", [
    ("El vendedor me trató mal y además quiero saber cuánto dura la garantía de la lavadora",
     "queja_trato", "12 meses"),
    ("Qué garantía tiene una tostadora? Me atendió mal el vendedor", "queja_trato", "6 meses"),
    ("Me cobraron dos veces. Por cierto, cuánto tarda el envío a otra ciudad?", "disputa_facturacion", "5-7 días"),
    ("Disputo el cobro de mi factura, y mi pedido ORD-1003 cuándo llega?", "disputa_facturacion", "Procesando"),
    ("Voy a demandarlos. Mientras tanto, dónde está mi pedido ORD-1001?", "tema_legal", "En tránsito"),
    ("Quiero un reembolso de $900 y saber en cuánto tiempo se procesan los reembolsos",
     "reembolso_mayor_500", "5-10 días hábiles"),
    ("Quiero que me reembolsen $750 de la estufa; la garantía cubre algo así?", "reembolso_mayor_500", "12 meses"),
])
def test_responde_lo_permitido_y_luego_deriva(agente, pregunta, categoria, debe_contener):
    r = agente.responder(pregunta)
    assert r.estado == "escalado" and categoria in r.escalamientos
    assert debe_contener in r.texto
    assert r.texto.rstrip().endswith(r.texto.split("\n\n")[-1])      # la derivación va al final
    assert CONTACTO in r.texto.split("\n\n")[-1]


def test_si_no_hay_parte_permitida_solo_deriva(agente):
    r = agente.responder("Mi lavadora se rompió a los 3 meses, quiero mi dinero de $1.000 de vuelta y hablar con un abogado")
    assert r.estado == "escalado" and "\n\n" not in r.texto and CONTACTO in r.texto


def test_un_solo_reclamo_no_arrastra_documentos_de_contacto(agente):
    r = agente.responder("El vendedor me trató mal")
    assert r.texto.count(CONTACTO) == 1 and "contacto" not in r.fuentes
