"""Validación de lo que escribe el modelo: sin consejos ni pasos inventados, y sin restos de citas rotas.
Los textos son respuestas reales de `qwen2.5:7b` a preguntas del banco de frases."""

import pytest

from tiendahogar.redaccion import limpiar_citas, problema_de_salida, armar_prompt
from tiendahogar.rag import cargar_indice

INDICE = cargar_indice()


def prompt_de(pregunta: str) -> str:
    resultados = INDICE.buscar(pregunta)
    if not resultados:      # sin embeddings el recuperador no ve la pregunta del teléfono: se le da el documento de contacto
        resultados = [r for r in INDICE.puntuar("contacto canal queja facturacion legal") if r.fragmento.documento == "contacto"]
    return armar_prompt(pregunta, resultados, [])


INVENTADAS = [
    ("Me compre una estufa hace 7 meses pero se empezó a despegar una pata, me lo cubre la garantía?",
     "Sí, la garantía de 12 meses cubre el defecto de fábrica en tu estufa, por lo que deberías contactar a soporte para "
     "el proceso de reparación o reemplazo. [garantia]"),
    ("Adquirí una plancha hace un par de meses pero se apaga sola, me cubre el service oficial?",
     "Tu plancha tiene garantía de 6 meses desde la fecha de compra. El problema que describes podría estar dentro del "
     "periodo de garantía, por lo que deberías contactar al service oficial para que evalúe la situación. [garantia]"),
]

CORRECTAS = [
    ("Me compré un refrigerador, cuanto tiene de garantía?", "Tu refrigerador tiene garantía de 12 meses desde la fecha de compra. [garantia]"),
    ("Hace 10 meses compre un refrigerador y quiero devolverlo",
     "Según nuestra política de devoluciones, los productos deben devolverse dentro de 30 días de la compra. Como han pasado "
     "10 meses, solo se aceptarían devoluciones si los productos presentan un defecto cubierto por garantía. [devoluciones]"),
    ("Tienen garantía extendida?", "No, la garantía extendida no se menciona en la política de garantía proporcionada. [garantia]"),
    ("Cuál es el teléfono de atención al cliente?",
     "El teléfono de atención al cliente no se encuentra en la información proporcionada. Para cualquier consulta, puedes "
     "dirigirte a soporte@tiendahogar.example. [contacto]"),
]


@pytest.mark.parametrize("pregunta,texto", INVENTADAS)
def test_se_descarta_una_respuesta_con_consejos_o_pasos_inventados(pregunta, texto):
    assert "inventados" in (problema_de_salida(texto, prompt_de(pregunta)) or "")


@pytest.mark.parametrize("pregunta,texto", CORRECTAS)
def test_se_acepta_una_respuesta_fiel_a_los_documentos(pregunta, texto):
    assert problema_de_salida(texto, prompt_de(pregunta)) is None


def test_una_referencia_a_una_cita_rota_se_borra_entera():
    texto = "Según la [Política de Garantía], la plancha tiene una garantía de 6 meses. [garantia]"
    assert limpiar_citas(texto, ["garantia"]) == "La plancha tiene una garantía de 6 meses. [garantia]"
    assert limpiar_citas("Según la, tu plancha tiene 6 meses.", ["garantia"]).startswith("Tu plancha tiene 6 meses.")
    assert limpiar_citas("Según nuestra política, 6 meses. [garantia]", ["garantia"]) == "Según nuestra política, 6 meses. [garantia]"


def test_una_cita_en_el_medio_pasa_al_final():
    assert limpiar_citas("Según la [garantia], la licuadora tiene garantía de 6 meses.", ["garantia"]) == \
        "La licuadora tiene garantía de 6 meses. [garantia]"


@pytest.mark.parametrize("pregunta,texto", [
    ("Mi lavadora tiene 8 meses y se rompió, aplica la garantía y puedo devolverla?",
     "Sí, aplica la garantía. No puedes devolverla, solo puedes solicitar el arreglo o reemplazo según la garantía. [garantia]"),
    ("Mi licuadora falla, qué hago?", "La garantía cubre el defecto, así que van a reparar tu licuadora. [garantia]"),
    ("Mi plancha no calienta", "Con la garantía podés pedir el canje por una plancha nueva. [garantia]"),
])
def test_se_descarta_un_remedio_que_los_documentos_no_ofrecen(pregunta, texto):
    assert "remedio" in (problema_de_salida(texto, prompt_de(pregunta)) or "")


def test_si_el_cliente_nombra_el_remedio_el_modelo_puede_decir_que_no_tiene_esa_informacion():
    pregunta = "Me pueden reemplazar la licuadora?"
    texto = "No tengo información sobre el reemplazo de licuadoras. [garantia]"
    assert problema_de_salida(texto, prompt_de(pregunta)) is None


@pytest.mark.parametrize("texto", [
    "Los reembolsos se procesan en 5-10 días hábiles. Se reembolsa al mismo método de pago original. [reembolsos]",
    "El reembolso se acredita en 5-10 días hábiles después de recibir el producto devuelto. [reembolsos]",
])
def test_repetir_lo_que_dice_el_documento_no_es_una_promesa(texto):
    assert problema_de_salida(texto, prompt_de("Cuánto tarda un reembolso y a qué método de pago me lo devuelven?")) is None


@pytest.mark.parametrize("texto", [
    "Tu reembolso se aprobó y se acredita en 5-10 días hábiles. [reembolsos]",
    "Listo, te lo reembolsamos hoy mismo al mismo método de pago original. [reembolsos]",
    "Tu reembolso fue aprobado y se procesa en 5-10 días hábiles. [reembolsos]",
])
def test_decir_que_algo_ya_esta_aprobado_o_hecho_si_es_una_promesa(texto):
    assert "promesa" in (problema_de_salida(texto, prompt_de("Cuánto tarda un reembolso?")) or "")
