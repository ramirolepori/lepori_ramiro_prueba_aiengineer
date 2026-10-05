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
