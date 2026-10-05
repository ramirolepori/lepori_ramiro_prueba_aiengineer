"""El plazo de devolución del Doc 2 aplicado por código a lo que el cliente dice que pasó desde la compra."""

import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.plazos import dias_desde_la_compra, garantia_del_producto, nota_de_devolucion


@pytest.mark.parametrize("texto,dias", [
    ("Quiero devolver mi heladera que compre hace 25 días", 25),
    ("Compré mi tostadora hace 45 días y la quiero devolver", 45),
    ("Compré hace dos meses y quiero cambiarlo", 60),
    ("Hace 3 semanas compré una tostadora, me la aceptan de vuelta?", 21),
    ("Ayer fui al local e hice una compra por $499,99 y quería devolverlo", 1),
    ("Compré una licuadora hace 40 días y no enciende, la devuelvo o hay garantía?", 40),
    ("Quiero devolver mi licuadora Antigüedad: hace 3 semanas.", 21),
    ("Hace 10 meses compré un refrigerador y quiero hacer la devolución", 300),
])
def test_dias_desde_la_compra(texto, dias):
    assert dias_desde_la_compra(texto) == dias


@pytest.mark.parametrize("texto", [
    "hace 6 días que envié el producto para que me devuelvan el dinero",         # días de espera de un reembolso
    "Cuánto dura la garantía de una licuadora comprada hace 3 meses?",           # no pide devolver
    "Devolví la heladera hace 8 días y todavía no me reintegran",
    "Quiero devolver mi heladera",                                               # sin duración
])
def test_no_cuenta_cuando_los_dias_son_de_otra_cosa(texto):
    assert dias_desde_la_compra(texto) is None


def test_la_nota_repite_el_documento():
    assert "defecto cubierto por la garantía" in nota_de_devolucion(31)
    assert "sin usar y en su empaque original" in nota_de_devolucion(30)


@pytest.mark.parametrize("pregunta,esperado", [
    ("Compré mi tostadora hace 45 días pero no la saqué del empaque, la quiero devolver", "pasaron más de 30 días"),
    ("Quiero devolver mi heladera que compré hace 25 días, solo la conecté para probarla", "dentro de los 30 días"),
])
def test_el_agente_agrega_la_cuenta_a_su_respuesta(pregunta, esperado):
    assert esperado in AgenteSoporte().responder(pregunta).texto


class LLMQueNoDebeUsarse:
    llamadas = 0

    def generar(self, sistema, prompt):
        LLMQueNoDebeUsarse.llamadas += 1
        return "No se aceptan devoluciones después de 30 días si el producto no fue usado. [devoluciones]"


def test_el_plazo_se_responde_por_codigo_y_no_con_el_modelo():
    r = AgenteSoporte(llm=LLMQueNoDebeUsarse()).responder("Compré mi tostadora hace 45 días pero no la saqué del empaque, la quiero devolver")
    assert LLMQueNoDebeUsarse.llamadas == 0
    assert "solo se acepta si el producto tiene un defecto cubierto por la garantía" in r.texto and "[devoluciones]" in r.texto


def test_con_mas_de_30_dias_y_una_falla_tambien_da_lo_que_dice_la_garantia():
    r = AgenteSoporte().responder("Compré una licuadora hace 40 días y no enciende, la devuelvo o hay garantía?")
    assert "pasaron más de 30 días" in r.texto and "6 meses" in r.texto and "[garantia]" in r.texto


@pytest.mark.parametrize("pregunta", [
    "Compré en liquidación hace 10 días y quiero devolver el producto",
    "Compré una heladera personalizada hace 20 días y la quiero devolver",
    "Compré una heladera que hicieron solo para mi hace 5 días y la quiero devolver",
])
def test_un_producto_que_no_se_devuelve_nunca_no_recibe_la_cuenta_de_los_dias(pregunta):
    texto = AgenteSoporte().responder(pregunta).texto
    assert "dentro de los 30 días" not in texto and "pasaron más de 30 días" not in texto


# --- el tiempo dicho de otras formas: "tiene 8 meses", "de 14 meses", "de hace 40 días" ---------------------------------------------

@pytest.mark.parametrize("texto,dias", [
    ("Mi lavadora tiene 8 meses y se rompió, puedo devolverla?", 240),
    ("Mi licuadora tiene 45 días y falla, la puedo devolver?", 45),
    ("Mi refrigeradora de 14 meses falló, puedo devolverla?", 420),
    ("Quiero devolver mi lavadora de hace 40 días, está defectuosa", 40),
    ("La lavadora de mi mamá tiene 3 meses y se rompió, puede devolverla?", 90),
    ("Mi tostadora tiene 2 años, la puedo devolver?", 730),
    ("La heladera que compré tiene dos semanas, la puedo cambiar?", 14),
])
def test_la_edad_del_producto_dicha_de_otra_forma_tambien_cuenta(texto, dias):
    assert dias_desde_la_compra(texto) == dias


@pytest.mark.parametrize("texto", [
    "Mi licuadora tiene 6 meses de garantía, puedo devolverla?",              # el plazo de la garantía, no la edad
    "Mi hija tiene 8 meses y le regalaron una plancha, puedo devolverla?",    # la edad de otra cosa
    "Mi licuadora se rompió hace 3 días, la puedo devolver?",                 # la fecha de la falla, no de la compra
    "Tengo 30 días para devolver mi heladera?",
])
def test_no_se_toma_por_la_edad_del_producto_lo_que_es_otra_cosa(texto):
    assert dias_desde_la_compra(texto) is None


@pytest.mark.parametrize("texto,dentro,vencida", [
    ("Mi lavadora tiene 8 meses y se rompió, tengo garantía?", True, False),
    ("Mi licuadora tiene 7 meses y falla, tengo garantía?", False, True),
    ("Compré una estufa hace 2 años, se rompió, qué puedo hacer?", False, True),
    ("Tengo una plancha de 3 meses que no calienta, la garantía la cubre?", True, False),
    ("Mi lavarropas de 5 meses no centrifuga, puedo usar la garantía?", True, False),
    ("Compré una heladera hace 12 meses y dejó de enfriar, tengo garantía?", True, False),
])
def test_la_garantia_se_calcula_con_el_producto_y_el_tiempo(texto, dentro, vencida):
    g = garantia_del_producto(texto)
    assert (g is not None and "todavía estás dentro" in g) is dentro and (g is not None and "ya pasó ese plazo" in g) is vencida


@pytest.mark.parametrize("texto", [
    "Mi licuadora tiene 6 meses de garantía, es verdad?",                     # no es la edad
    "Cuánto dura la garantía de la plancha de 6 meses?",                      # ambiguo: se da el documento
    "Mi licuadora se rompió hace 3 días, tengo garantía?",                    # "hace 3 días" no es la compra
    "Compré hace 8 meses una heladera y una licuadora, tienen garantía?",     # dos productos con plazos distintos
    "Cuánto dura la garantía de una refrigeradora?",                          # sin tiempo
    "Compré hace 8 meses, tengo garantía?",                                   # sin producto
])
def test_la_garantia_no_se_calcula_si_falta_o_es_ambiguo_algun_dato(texto):
    assert garantia_del_producto(texto) is None


def test_con_la_devolucion_en_juego_una_garantia_vencida_dice_que_no_se_acepta():
    g = garantia_del_producto("Mi refrigeradora de 14 meses falló, puedo devolverla?", devolucion=True)
    assert g.endswith("ya pasó ese plazo, así que la devolución no se acepta.")
    assert "no se acepta" not in garantia_del_producto("Mi refrigeradora de 14 meses falló, tengo garantía?")


class LLMQueNoSeLlama:
    def __init__(self):
        self.llamadas = 0

    def generar(self, sistema, prompt):
        self.llamadas += 1
        return "Sí, aplica la garantía. No puedes devolverla, solo puedes solicitar el arreglo o reemplazo según la garantía."


@pytest.mark.parametrize("pregunta,esperado,no_esperado", [
    ("Mi lavadora tiene 8 meses y se rompió, aplica la garantía y puedo devolverla?",
     ["pasaron más de 30 días", "12 meses", "con 8 meses todavía estás dentro"], ["no se acepta", "arreglo", "reemplazo"]),
    ("Mi licuadora tiene 7 meses y falla, puedo devolverla o usar la garantía?",
     ["pasaron más de 30 días", "6 meses", "ya pasó ese plazo", "la devolución no se acepta"], ["arreglo", "reemplazo"]),
    ("Mi refrigeradora de 14 meses falló, puedo devolverla?",
     ["12 meses", "ya pasó ese plazo", "la devolución no se acepta"], ["arreglo", "reemplazo"]),
    ("Quiero devolver mi lavadora de hace 40 días, está defectuosa",
     ["pasaron más de 30 días", "con 40 días todavía estás dentro"], ["no se acepta"]),
])
def test_garantia_mezclada_con_devolucion_se_responde_por_codigo_con_cualquier_redaccion(pregunta, esperado, no_esperado):
    llm = LLMQueNoSeLlama()
    r = AgenteSoporte(llm=llm).responder(pregunta)
    assert llm.llamadas == 0, "es una cuenta de los documentos: no la hace el modelo"
    assert all(e in r.texto for e in esperado) and not any(n in r.texto for n in no_esperado), r.texto
    assert r.estado == "respondido" and {"devoluciones", "garantia"} >= set(r.fuentes)


# --- el plazo de la garantía no es la edad del producto, y "un año y medio" no es un año --------------------------------------------

@pytest.mark.parametrize("texto", [
    "La garantía de la licuadora tiene 6 meses, es así?",
    "La garantía de la heladera tiene 12 meses?",
    "La licuadora tiene 6 meses de garantía, es así?",
])
def test_el_plazo_de_la_garantia_dicho_como_tiene_n_meses_no_se_toma_por_la_edad(texto):
    assert garantia_del_producto(texto) is None and dias_desde_la_compra(texto + " la puedo devolver?") is None


def test_la_garantia_de_la_lavadora_que_tiene_8_meses_si_es_la_edad():
    assert "con 8 meses todavía estás dentro" in garantia_del_producto("Cuál es la garantía de la lavadora que tiene 8 meses y se rompió?")


@pytest.mark.parametrize("texto,vencida,dicho", [
    ("Mi lavadora tiene un año y medio y se rompió, tengo garantía?", True, "con un año y medio"),
    ("Compré una heladera hace 1 año y 2 meses y se rompió, tengo garantía?", True, "con 1 año y 2 meses"),
    ("Mi heladera tiene 1 año y pico, tengo garantía?", True, "con 1 año y pico"),
    ("Mi plancha tiene 3 meses y medio y no calienta, tengo garantía?", False, "con 3 meses y medio"),
    ("Mi estufa tiene 11 meses y 3 semanas y se rompió, tengo garantía?", False, "con 11 meses y 3 semanas"),
])
def test_las_duraciones_compuestas_se_suman(texto, vencida, dicho):
    g = garantia_del_producto(texto)
    assert dicho in g and ("ya pasó ese plazo" in g) is vencida


@pytest.mark.parametrize("texto,dias", [
    ("Mi lavadora tiene 2 años y 3 meses, se rompió, la puedo devolver?", 820),
    ("Compré una lavadora hace 2 semanas y 3 días, la puedo devolver?", 17),
    ("Compré hace 3 meses y quiero devolver mi licuadora", 90),                  # "y quiero" no es parte de la duración
])
def test_los_dias_tambien_suman_las_partes(texto, dias):
    assert dias_desde_la_compra(texto) == dias


# --- cuándo lo recibió: "me llegó hoy", "lo recibí ayer", "llegó hace 5 días" ---------------------------------------------------------

@pytest.mark.parametrize("texto,dias", [
    ("Quiero devolver mi licuadora. Antigüedad: Me llego hoy.", 0),
    ("Me llegó hoy la licuadora y quiero devolverla", 0),
    ("Lo recibí hoy y no lo usé, lo devuelvo?", 0),
    ("Me llegó recién, lo puedo devolver?", 0),
    ("Me llegó ayer, quiero devolver mi heladera", 1),
    ("Mi pedido llegó hace 5 días y está fallado, puedo devolverlo?", 5),
    ("Me llegó hoy un mail, quiero devolver mi licuadora que compré hace 20 días", 20),      # la duración explícita manda
])
def test_cuando_lo_recibio_tambien_cuenta(texto, dias):
    assert dias_desde_la_compra(texto) == dias


# --- con un pedido en la consulta: el estado, la cuenta y la garantía del producto del pedido los pone el código -----------------------

def charlar_con(llm, *mensajes):
    from tiendahogar.sesion import Sesion
    a, s = AgenteSoporte(llm=llm), Sesion()
    return s, [a.responder(m, s) for m in mensajes]


def llm_nuevo():
    return LLMQueNoSeLlama()


def test_el_pedido_que_llego_fallado_se_responde_por_codigo_en_los_dos_turnos():
    llm = llm_nuevo()
    s, (r1, r2) = charlar_con(llm, "Mi pedido ORD-1002 llegó fallado, puedo devolverlo o usar la garantía?", "Me llego hoy")
    assert "figura como Entregado" in r1.texto and "dentro de 30 días de la compra" in r1.texto          # la devolución
    assert "La garantía de tu licuadora es de 6 meses" in r1.texto                                      # y la garantía del pedido
    assert "¿Hace cuánto lo compraste?" in r1.texto and s.pendiente is None
    assert "figura como Entregado" in r2.texto and "estás dentro de los 30 días" in r2.texto
    assert "La garantía de tu licuadora es de 6 meses" in r2.texto and "¿Hace cuánto" not in r2.texto
    assert llm.llamadas == 0 and "arreglo" not in r1.texto + r2.texto


def test_el_pedido_entregado_hace_mas_de_30_dias_hace_la_cuenta_de_la_garantia_del_producto():
    _, (r,) = charlar_con(llm_nuevo(), "Quiero devolver mi pedido ORD-1002 que recibí hace 40 días")
    assert "pasaron más de 30 días" in r.texto and "con 40 días todavía estás dentro" in r.texto
    _, (r,) = charlar_con(llm_nuevo(), "Mi pedido ORD-1002 lo recibí hace 8 meses y se rompió, puedo devolverlo?")
    assert "6 meses" in r.texto and "ya pasó ese plazo, así que la devolución no se acepta" in r.texto


@pytest.mark.parametrize("pregunta,esperado", [
    ("Quiero devolver mi tostadora ORD-1004", "figura como cancelado"),
    ("Quiero devolver ORD-1003 o usar la garantía", "todavía no figura como entregado"),
    ("Quiero devolver mi pedido ORD-9999", "No encontré ningún pedido"),
])
def test_un_pedido_cancelado_en_preparacion_o_inexistente_tambien_se_responde_por_codigo(pregunta, esperado):
    llm = llm_nuevo()
    _, (r,) = charlar_con(llm, pregunta)
    assert esperado in r.texto and llm.llamadas == 0


def test_con_un_pedido_pero_sobre_reembolsos_el_modelo_sigue_redactando():
    llm = llm_nuevo()
    charlar_con(llm, "Mi pedido ORD-1002 llegó fallado, quiero que me devuelvan la plata, cuánto tarda el reembolso?")
    assert llm.llamadas >= 1
