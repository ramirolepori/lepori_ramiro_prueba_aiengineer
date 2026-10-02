import pytest

from tiendahogar.rag import cargar_indice


@pytest.fixture(scope="module")
def indice():
    return cargar_indice()


def test_indexa_los_cinco_documentos(indice):
    assert {f.documento for f in indice.fragmentos} == {"garantia", "devoluciones", "envios", "reembolsos", "contacto"}


def test_pregunta_de_garantia_trae_el_documento_de_garantia(indice):
    res = indice.buscar("Cuánto dura la garantía de una licuadora?")
    assert res[0].fragmento.documento == "garantia"


@pytest.mark.parametrize("pregunta,documento", [
    ("Puedo devolver un producto en liquidación?", "devoluciones"),
    ("Cuánto tarda el envío a otra ciudad?", "envios"),
    ("Hacen envíos internacionales?", "envios"),
    ("En cuánto tiempo me reembolsan?", "reembolsos"),
    ("Cuánto tarda un reembolso?", "reembolsos"),
    ("A qué mail escribo por un tema legal?", "contacto"),
])
def test_recupera_el_documento_correcto(indice, pregunta, documento):
    assert indice.buscar(pregunta)[0].fragmento.documento == documento


def test_garantia_mezclada_con_devolucion_trae_ambos(indice):
    docs = {r.fragmento.documento for r in indice.buscar("Mi tostadora tiene 8 meses y se rompió, la puedo devolver?")}
    assert {"garantia", "devoluciones"} <= docs


@pytest.mark.parametrize("pregunta", [
    "Cuál es la capital de Francia?",
    "Qué hora es?",
    "Recomendame una película",
    "Cuánto cuesta una refrigeradora?",
    "Cómo cocino arroz en la estufa?",
    "Qué marcas de lavadoras venden?",
])
def test_fuera_de_alcance_no_supera_el_umbral(indice, pregunta):
    assert indice.buscar(pregunta) == []
