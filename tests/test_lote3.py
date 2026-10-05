"""Casos que mostró el lote 3 (el definitivo de Ramiro): se corrigieron con reglas generales, no copiando las frases."""

import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.redaccion import para_el_cliente
from tiendahogar.guardrails import evaluar
from tiendahogar.lugares import resolver_lugares
from tiendahogar.pedidos import extraer_identificadores_raros
from tiendahogar.sesion import Sesion


@pytest.fixture(scope="module")
def agente():
    return AgenteSoporte()


# --- quejas de trato dichas de otra forma ---------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "La persona que nos atendió lo hizo tan mal que mi novia salió llorando",
    "Ayer un empleado me tiró un vaso de agua en la cara",
    "Una persona que trabaja ahí tuvo actitudes que me faltaron el respeto",
    "Me faltaron el respeto en el local",
    "Nos atendieron muy mal",
])
def test_queja_de_trato_en_otras_palabras(texto):
    assert "queja_trato" in [e.categoria for e in evaluar(texto)]


# --- identificadores con formato raro dentro de una frase -------------------------------------------------------

@pytest.mark.parametrize("texto,literal", [
    ("ordené una licuadora (DOR--1002) y quería saber el estado", "DOR--1002"),
    ("Mi compra es la XY_5500, cuándo llega?", "XY_5500"),
])
def test_codigo_raro_con_doble_guion_o_dentro_de_un_parentesis(agente, texto, literal):
    assert extraer_identificadores_raros(texto) == [literal]
    assert "No encontré" in agente.responder(texto).texto


def test_un_modelo_de_producto_no_es_un_pedido():
    assert extraer_identificadores_raros("mi licuadora modelo XT-5000 falla") == []


# --- lugares fuera de la muestra y con una pista de envío --------------------------------------------------------

def test_la_quiaca_esta_en_el_diccionario(agente):
    assert [l.nombre for l in resolver_lugares("Puede ser que a la quiaca las compras tarden 4 días en llegar?")] == ["La Quiaca"]
    r = agente.responder("Puede ser que a la quiaca las compras tarden 4 días en llegar?")
    assert "5-7 días hábiles" in r.texto and "4 días" not in r.texto


def test_un_lugar_desconocido_tras_una_pista_de_envio_se_repregunta(agente):
    lugares = resolver_lugares("a Zapala las compras tardan?")
    assert [(l.nombre, l.tipo) for l in lugares] == [("Zapala", "desconocido")]


# --- agradecimientos y comentarios positivos ---------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "Ayer compré mi licuadora ORD-1002 y salió todo bien, estoy muy agradecido",
    "Hace unos días compré mi refrigerador y estoy muy conforme con la compra",
    "Me atendió uno de los chicos y quería felicitarlos porque me atendió muy amablemente",
])
def test_un_agradecimiento_se_agradece_y_no_se_responde_con_una_politica(agente, texto):
    r = agente.responder(texto)
    assert r.texto.startswith("¡Gracias por tu mensaje!") and r.fuentes == [] and r.pedidos == []


@pytest.mark.parametrize("texto", [
    "Muchas gracias, ahora cuánto tarda el envío a Rosario?",
    "Estoy agradecido pero quiero devolver la heladera",
    "Excelente atención, pero el producto llegó roto",
])
def test_un_agradecimiento_con_un_pedido_o_un_problema_sigue_su_curso(agente, texto):
    assert not agente.responder(texto).texto.startswith("¡Gracias por tu mensaje!")


# --- no le dieron la factura o el comprobante ---------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "Ayer hice una compra pero no me dieron factura de compra",
    "No recibí el comprobante de la compra",
    "Me vendieron una licuadora sin factura",
])
def test_sin_factura_dice_que_no_tiene_la_informacion_y_ofrece_derivar(agente, texto):
    r = agente.responder(texto)
    assert r.estado == "respondido" and "Mis documentos no dicen" in r.texto
    assert "¿Querés hacer un reclamo?" in r.texto and "soporte@tiendahogar.example" in r.texto


def test_sin_comprobante_y_con_garantia_da_lo_que_dice_la_garantia(agente):
    r = agente.responder("Como puedo hacer valer mi garantía si no recibí comprobante de compra")
    assert "12 meses" in r.texto and "6 meses" in r.texto and "¿Querés hacer un reclamo?" in r.texto


def test_si_quiere_hacer_el_reclamo_se_deriva(agente):
    s = Sesion()
    agente.responder("Ayer hice una compra pero no me dieron factura de compra", s)
    r = agente.responder("sí", s)
    assert r.estado == "escalado" and r.escalamientos == ["disputa_facturacion"] and "soporte@tiendahogar.example" in r.texto


def test_si_no_quiere_hacer_el_reclamo_no_se_deriva(agente):
    s = Sesion()
    agente.responder("No me dieron el comprobante de compra", s)
    r = agente.responder("no, gracias", s)
    assert r.estado == "respondido" and s.pendiente is None and "soporte@" not in r.texto


# --- productos hechos a pedido y notas internas de los documentos ------------------------------------------------------

def test_un_producto_hecho_a_pedido_no_pregunta_cuando_se_compro(agente):
    r = agente.responder("Compré una heladera que hicieron solo para mi, de color púrpura, pero la quiero devolver")
    assert "¿Hace cuánto" not in r.texto and "personalizados" in r.texto


def test_las_indicaciones_para_el_agente_no_se_le_muestran_al_cliente():
    assert para_el_cliente("Reembolsos mayores a $500 requieren aprobación de un supervisor humano — el agente no debe "
                            "aprobarlos automáticamente.") == "Reembolsos mayores a $500 requieren aprobación de un supervisor humano."
    assert "asistente de IA" not in para_el_cliente("referido a un agente humano en soporte@tiendahogar.example — el asistente de IA no debe intentar resolver estos casos.")


def test_el_contacto_no_se_repite_si_la_respuesta_ya_trae_el_correo():
    from tiendahogar.redaccion import completar_cobertura
    from tiendahogar.rag import Fragmento, Resultado
    contacto = Resultado(Fragmento("contacto#0", "contacto", "# Canales de contacto\n\nEscribir a soporte@tiendahogar.example"), 1.0, 1.0)
    texto, agregados = completar_cobertura("Escribí a soporte@tiendahogar.example", [contacto], "con quien me contacto")
    assert agregados == []


# --- preguntas por el canal: frase fija, sin motivos inventados ------------------------------------------------------

@pytest.mark.parametrize("pregunta", [
    "Hace unos días que no recibo mi reembolso, con quien me puedo contactar?",
    "Hace 11 días que estoy esperando mi reembolso (ya fue aprobado), con quien me tengo que contactar?",
    "A qué mail le escribo si tengo un problema con la facturación?",
])
def test_una_pregunta_por_el_canal_se_responde_con_el_correo_y_sin_motivos_inventados(agente, pregunta):
    texto = agente.responder(pregunta).texto
    assert "Para hablar con una persona, escribí a soporte@tiendahogar.example" in texto
    assert "quejas sobre reembolsos" not in texto and "asistente de IA" not in texto


def test_una_pregunta_por_el_canal_no_se_responde_con_el_modelo():
    class LLM:
        llamadas = 0

        def generar(self, sistema, prompt):
            LLM.llamadas += 1
            return "Para quejas sobre reembolsos, el cliente debe ser referido a un agente humano. [contacto]"

    r = AgenteSoporte(llm=LLM()).responder("Con quien tengo que hablar si tuve una disputa con un empleado?")
    assert LLM.llamadas == 0 and "Para hablar con una persona" in r.texto
