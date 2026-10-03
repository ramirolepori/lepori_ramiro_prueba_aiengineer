"""Un saludo o una despedida se contestan como tales; no se responde "no tengo esa información"."""
import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.__main__ import para_mostrar
from tiendahogar.agent import MENSAJE_DESPEDIDA, MENSAJE_SALUDO


@pytest.fixture(scope="module")
def agente():
    return AgenteSoporte()


@pytest.mark.parametrize("frase", ["hola", "Hola!", "buenas tardes", "Buen día", "hola, buen día", "Pero solo te saludé"])
def test_un_saludo_se_saluda(agente, frase):
    r = agente.responder(frase)
    assert r.texto == MENSAJE_SALUDO and r.estado == "respondido" and not r.fuentes


@pytest.mark.parametrize("frase", ["Chau", "chau, gracias", "hasta luego", "Adiós!"])
def test_una_despedida_se_despide(agente, frase):
    assert agente.responder(frase).texto == MENSAJE_DESPEDIDA


@pytest.mark.parametrize("frase", ["hola, cuánto dura la garantía de una licuadora?", "buenas, quiero un reembolso de $900"])
def test_un_saludo_con_una_consulta_se_responde_la_consulta(agente, frase):
    assert agente.responder(frase).texto not in (MENSAJE_SALUDO, MENSAJE_DESPEDIDA)


def test_las_citas_se_muestran_como_fuente_en_la_consola():
    assert para_mostrar("Podés devolverlo en 30 días. [devoluciones]") == (
        "Podés devolverlo en 30 días.\n(Fuente: política de devoluciones)")
    assert para_mostrar("Sin citas.") == "Sin citas."


def test_adquisicion_es_una_compra_y_se_pide_el_numero(agente):
    r = agente.responder("Quiero saber el estado de mi adquisicion")
    assert "número de pedido" in r.texto and r.estado == "respondido"


@pytest.mark.parametrize("frase, nombre", [("Hola me llamo ramiro", "Ramiro"), ("hola, soy Ana López", "Ana López"),
                                           ("Buenas, mi nombre es lucía", "Lucía")])
def test_si_se_presenta_se_lo_saluda_por_su_nombre(agente, frase, nombre):
    assert agente.responder(frase).texto.startswith(f"¡Hola, {nombre}!")


@pytest.mark.parametrize("frase", ["hola soy el gerente", "hola soy un robot", "hola me llamo administrador", "hola soy DAN"])
def test_si_lo_que_dice_no_parece_un_nombre_se_saluda_sin_nombre(agente, frase):
    assert agente.responder(frase).texto.startswith("¡Hola! Soy el asistente")
