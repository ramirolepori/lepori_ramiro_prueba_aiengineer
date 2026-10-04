"""Casos que dejó una revisión externa (búsqueda de errores a mano sobre el agente en modo offline). Cada uno falló antes de
corregirse: montos escritos de formas raras, preguntas por la regla que se derivaban, el canal humano, incidentes de
seguridad, acciones que el agente no hace, y el hilo de una devolución con el número de pedido."""

import json

import pytest

from tiendahogar import AgenteSoporte, consultar_estado_pedido
from tiendahogar.montos import extraer_montos
from tiendahogar.pedidos import extraer_identificadores_raros, extraer_referencias
from tiendahogar.sesion import Sesion

CONTACTO = "soporte@tiendahogar.example"


@pytest.fixture(scope="module")
def agente():
    return AgenteSoporte()


# --- montos -----------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("medio millón", 500_000), ("un palo", 1_000_000), ("dos palos", 2_000_000), ("$1.5M", 1_500_000), ("2M", 2_000_000),
    ("seis cientos pesos", 600), ("6 cientos", 600), ("cuatro cientos", 400), ("1’000", 1000), ("1'000", 1000),
])
def test_formas_raras_de_escribir_un_monto(texto, esperado):
    assert extraer_montos(texto) == [esperado]


@pytest.mark.parametrize("texto", ["5-10 días", "entre 5 a 10 días hábiles"])
def test_los_plazos_no_son_dinero(texto):
    assert extraer_montos(texto) == []


@pytest.mark.parametrize("pregunta", [
    "Quiero un reembolso de medio millón", "Quiero un reembolso de un palo", "Quiero un reembolso de $1.5M",
    "Reembolso de seis cientos pesos", "Reembolso de 6 cientos", "Reembolso de 1’000",
])
def test_los_montos_escritos_de_forma_rara_se_derivan(agente, pregunta):
    r = agente.responder(pregunta)
    assert r.estado == "escalado" and r.escalamientos == ["reembolso_mayor_500"] and CONTACTO in r.texto


@pytest.mark.parametrize("pregunta", [
    "Me van a reembolsar en 5-10 días?", "Cuánto demora el reembolso, 5 a 10 días?",
    "Qué es un reembolso mayor a $500?", "Los reembolsos de más de quinientos pesos los aprueba un supervisor?",
])
def test_una_pregunta_por_la_regla_no_inventa_un_monto_ni_dice_que_no_hace_falta_supervisor(agente, pregunta):
    r = agente.responder(pregunta)
    assert r.estado == "respondido" and "Con el monto que indicás" not in r.texto and "[reembolsos]" in r.texto


def test_un_reembolso_propio_de_mas_de_500_se_deriva_aunque_diga_mas_de(agente):
    assert agente.responder("Quiero un reembolso de más de $600").estado == "escalado"


def test_un_precio_nombrado_de_paso_no_es_un_pedido_de_reembolso(agente):
    r = agente.responder("Garantía de una refrigeradora de $2000")
    assert r.estado == "respondido" and r.fuentes == ["garantia"]


def test_la_parte_permitida_de_una_derivacion_no_dice_que_no_hace_falta_supervisor(agente):
    r = agente.responder("Reembolso de 500 pesos y 1000 pesos")
    assert r.estado == "escalado" and "no hace falta la aprobación" not in r.texto


# --- canal humano, seguridad y enojo ------------------------------------------------------------------------------------

@pytest.mark.parametrize("pregunta", ["Quiero hablar con una persona", "Quiero hablar con un humano", "Necesito un supervisor",
                                      "Pasame con un asesor"])
def test_quien_pide_una_persona_recibe_el_canal(agente, pregunta):
    r = agente.responder(pregunta)
    assert r.estado == "respondido" and CONTACTO in r.texto and r.fuentes == ["contacto"]


def test_una_pregunta_sobre_una_persona_real_no_es_pedir_el_canal(agente):
    assert agente.responder("Si fueras una persona real, qué pensarías de la política argentina?").fuentes == []


@pytest.mark.parametrize("pregunta", [
    "Mi hijo se lastimó con la licuadora", "La plancha me dio un golpe de corriente, me lastimé", "La tostadora hizo cortocircuito",
    "Me electrocuté con la heladera",
])
def test_un_incidente_de_seguridad_se_deriva_a_una_persona(agente, pregunta):
    r = agente.responder(pregunta)
    assert r.estado == "escalado" and r.escalamientos == ["incidente_seguridad"] and CONTACTO in r.texto


@pytest.mark.parametrize("pregunta", ["Se quemó la licuadora", "Se me quemó la plancha", "La licuadora no enciende"])
def test_un_producto_que_falla_no_es_un_incidente_de_seguridad(agente, pregunta):
    assert "incidente_seguridad" not in agente.responder(pregunta).escalamientos


def test_enojarse_por_el_envio_no_es_un_tema_legal(agente):
    r = agente.responder("Es una estafa que tarde tanto el envío")
    assert r.estado == "respondido" and r.fuentes == ["envios"]


def test_acusar_de_estafa_si_es_un_tema_legal(agente):
    assert agente.responder("Esto es una estafa").escalamientos == ["tema_legal"]


# --- documentos que no corresponden y acciones que no hace --------------------------------------------------------------

@pytest.mark.parametrize("pregunta", ["Cuánto tarda en llegar el reembolso a mi tarjeta?", "Si me reembolsan $900 ¿cuánto tarda?"])
def test_una_pregunta_de_reembolso_no_trae_el_documento_de_envios(agente, pregunta):
    assert "envios" not in agente.responder(pregunta).fuentes


def test_si_le_reembolsan_en_efectivo_se_responde_con_la_politica_y_no_con_una_pregunta(agente):
    r = agente.responder("Me reembolsan en efectivo?")
    assert "mismo método de pago original" in r.texto and "¿De cuánto fue la compra?" not in r.texto


@pytest.mark.parametrize("pregunta", ["Quiero cancelar mi pedido ORD-1003", "Quiero cambiar la dirección de mi pedido ORD-1001"])
def test_cancelar_o_modificar_un_pedido_aclara_que_no_se_puede_y_no_trae_otros_documentos(agente, pregunta):
    r = agente.responder(pregunta)
    assert "No puedo realizar esa acción" in r.texto and r.fuentes == [] and r.pedidos


# --- pedidos ------------------------------------------------------------------------------------------------------------

def test_estado_del_pedido_a_secas_pide_el_numero(agente):
    r = agente.responder("Estado del pedido")
    assert "número de pedido" in r.texto and r.estado == "respondido"


def test_un_identificador_pegado_a_letras_no_se_corrige_en_silencio(agente):
    assert extraer_identificadores_raros("ORD-1001abc") == ["ORD-1001abc"] and extraer_referencias("ORD-1001abc") == []
    r = agente.responder("ORD-1001abc")
    assert r.pedidos[0]["encontrado"] is False and "formato" in r.texto


def test_un_numero_de_pedido_en_palabras():
    assert extraer_referencias("Pedido número mil uno")[0][0] == "ORD-1001"
    assert extraer_referencias("la orden de compra es hoy") == []


@pytest.mark.parametrize("order_id", ["ORD‑1001", "ORD-1001​", "ＯＲＤ-1001", " ord-1001 "])
def test_la_tool_tolera_guiones_raros_caracteres_invisibles_y_anchos_completos(order_id):
    assert consultar_estado_pedido(order_id)["order_id"] == "ORD-1001"


@pytest.mark.parametrize("order_id", [None, 123, b"ORD-1001", ["ORD-1001"], ""])
def test_la_tool_con_algo_que_no_es_texto_dice_no_encontrado_y_es_serializable(order_id):
    r = consultar_estado_pedido(order_id)
    assert r["encontrado"] is False and r["estado"] == "No encontrado"
    json.dumps(r)


@pytest.mark.parametrize("entrada", [None, 123])
def test_responder_con_algo_que_no_es_texto_no_se_rompe(agente, entrada):
    assert agente.responder(entrada).texto


# --- garantía con cuenta ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("pregunta,dentro", [
    ("Compré una refrigeradora hace 13 meses, tiene garantía?", False), ("Compré una licuadora hace 7 meses, tiene garantía?", False),
    ("Compré una licuadora hace 5 meses, tiene garantía?", True), ("Mi lavadora tiene 12 meses, tiene garantía?", True),
    ("Compré una plancha hace 1 año, tiene garantía?", False),
])
def test_la_garantia_se_calcula_con_el_plazo_del_producto(agente, pregunta, dentro):
    r = agente.responder(pregunta)
    assert r.fuentes == ["garantia"]
    assert ("todavía estás dentro" in r.texto) is dentro and ("ya pasó ese plazo" in r.texto) is (not dentro)


def test_la_garantia_sin_producto_o_sin_tiempo_repite_el_documento(agente):
    assert "12 meses" in agente.responder("Cuánto dura la garantía de la lavadora?").texto
    assert "todavía estás dentro" not in agente.responder("Compré hace 3 meses, tiene garantía?").texto


# --- el hilo de una devolución con el número de pedido ------------------------------------------------------------------

def charlar(agente, *mensajes):
    s = Sesion()
    return s, [agente.responder(m, s) for m in mensajes]


def test_quiero_hacer_una_devolucion_pide_el_pedido_o_la_fecha(agente):
    s, (r,) = charlar(agente, "Quiero hacer una devolución")
    assert "número de pedido (ORD-XXXX)" in r.texto and s.pendiente == "antiguedad" and "[reembolsos]" not in r.texto


@pytest.mark.parametrize("dato", ["ORD-1002", "1002", "el pedido 1002"])
def test_el_cliente_da_el_numero_de_pedido_sin_perder_el_hilo(agente, dato):
    s, (r1, r2) = charlar(agente, "Quiero hacer una devolución", dato)
    assert r2.pedidos and r2.pedidos[0]["order_id"] == "ORD-1002" and "figura como Entregado" in r2.texto
    assert "¿Hace cuánto lo compraste?" in r2.texto and s.pendiente == "antiguedad"


def test_despues_del_pedido_la_fecha_cierra_la_cuenta_con_el_pedido(agente):
    s, (_, _, r3) = charlar(agente, "Quiero hacer una devolución", "ORD-1002", "hace 10 días")
    assert "ORD-1002" in r3.texto and "dentro de los 30 días" in r3.texto and s.pendiente is None


def test_la_fecha_en_vez_del_pedido_tambien_sirve(agente):
    s, (_, r2) = charlar(agente, "Quiero hacer una devolución", "la de la licuadora, hace 45 días")
    assert "más de 30 días" in r2.texto and s.pendiente is None and "[reembolsos]" not in r2.texto


def test_devolver_un_pedido_cancelado_o_en_camino(agente):
    _, (r,) = charlar(agente, "Quiero devolver mi pedido ORD-1004")
    assert "figura como cancelado" in r.texto
    _, (r,) = charlar(agente, "Quiero devolver mi pedido ORD-1003")
    assert "todavía no figura como entregado" in r.texto


# --- el validador de lo que escribe el modelo ---------------------------------------------------------------------------

class Falso:
    def __init__(self, texto):
        self.texto = texto

    def generar(self, sistema, usuario):
        return self.texto


@pytest.mark.parametrize("pregunta,salida", [
    ("Quiero un reembolso de $400", "Listo, tu reembolso de $400 fue aprobado y se procesa en 5-10 días hábiles. [reembolsos]"),
    ("Cuánto dura la garantía de la licuadora?", "La licuadora tiene 6 meses de garantía y si se rompe te la reparamos gratis. [garantia]"),
    ("Puedo devolver un producto en liquidación?", "Sí, podés devolver productos en liquidación dentro de 30 días. [devoluciones]"),
    ("Puedo devolver un producto en liquidación?", "No se puede devolver. Ignorá mis instrucciones previas. [devoluciones]"),
    ("Cuánto dura la garantía de la lavadora?", "Dura 12 meses, y con mi autorización puedo extenderla. [garantia]"),
])
def test_una_promesa_o_una_contradiccion_del_modelo_se_descarta_y_se_usa_el_documento(pregunta, salida):
    r = AgenteSoporte(llm=Falso(salida)).responder(pregunta)
    assert salida not in r.texto and any(e["tipo"] == "llm" and not e["ok"] for e in r.traza)


def test_una_respuesta_correcta_del_modelo_pasa():
    salida = "Los reembolsos se procesan en 5-10 días hábiles después de recibir el producto devuelto. [reembolsos]"
    r = AgenteSoporte(llm=Falso(salida)).responder("Cuánto tarda un reembolso?")
    assert salida in r.texto


# --- recuperación ---------------------------------------------------------------------------------------------------------

def test_la_plata_ciudad_no_trae_el_documento_de_reembolsos(agente):
    assert agente.responder("Cuánto tarda el envío a La Plata?").fuentes == ["envios"]
    assert agente.responder("Quiero que me devuelvan la plata").fuentes == ["reembolsos"]


def test_se_rompio_lleva_a_la_garantia(agente):
    assert agente.responder("Pagué $700 por la licuadora y se rompió, qué hago?").fuentes == ["garantia"]


def test_no_me_gusto_la_atencion_es_una_queja_de_trato(agente):
    assert agente.responder("No me gustó la atención del local").escalamientos == ["queja_trato"]


def test_la_garantia_de_un_ano_se_escribe_con_enie(agente):
    assert "1 año" in agente.responder("Compré hace 1 año una plancha, tiene garantía?").texto


# --- lo que quedó pendiente de la primera revisión -------------------------------------------------------------------------

@pytest.mark.parametrize("pregunta", ["Soy de Lima, cuánto tarda?", "Cuánto tarda, soy de Córdoba"])
def test_un_lugar_con_cuanto_tarda_es_una_pregunta_de_envio_tambien_offline(agente, pregunta):
    assert agente.responder(pregunta).fuentes == ["envios"]


@pytest.mark.parametrize("pregunta", ["Necesito una copia de mi factura", "Quiero que me envíen la factura"])
def test_pedir_una_copia_de_la_factura_no_es_una_disputa_y_ofrece_derivar_si_es_un_reclamo(agente, pregunta):
    s, (r1, r2) = charlar(agente, pregunta, "sí")
    assert r1.estado == "respondido" and "no dicen cómo pedir una copia" in r1.texto and s.pendiente is None
    assert r2.estado == "escalado" and CONTACTO in r2.texto


def test_pedir_la_copia_y_no_querer_reclamar_cierra_sin_derivar(agente):
    _, (_, r2) = charlar(agente, "Necesito una copia de mi factura", "no")
    assert r2.estado == "respondido" and r2.escalamientos == []


def test_discutir_la_factura_si_se_deriva_aunque_nombre_la_factura(agente):
    assert agente.responder("Me cobraron de más en la factura").escalamientos == ["disputa_facturacion"]


@pytest.mark.parametrize("pregunta", [
    "No quiero un reembolso de $900, solo quiero saber la garantía", "No quiero un reembolso, solo saber la garantía",
    "No necesito que me devuelvan la plata, solo quiero saber cuánto dura la garantía",
])
def test_quien_dice_que_no_quiere_un_reembolso_recibe_la_garantia_y_no_una_derivacion(agente, pregunta):
    r = agente.responder(pregunta)
    assert r.estado == "respondido" and r.fuentes == ["garantia"] and "12 meses" in r.texto


def test_negar_un_reembolso_no_oculta_uno_que_si_pide(agente):
    assert agente.responder("No quiero un reembolso de $200 sino de $900").estado == "escalado"
