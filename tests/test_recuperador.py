import json
import os
import urllib.request
from pathlib import Path

import pytest

from tiendahogar.config import Config
from tiendahogar.embeddings import ClienteEmbeddings
from tiendahogar.evaluacion import cargar_casos_rag, medir_rag
from tiendahogar.llm import ErrorLLM
from tiendahogar.rag import FUERA_DE_ALCANCE, RecuperadorHibrido, cargar_indice, crear_recuperador


class ClienteFalso:
    """Embeddings de juguete: un vector por palabra clave, para controlar qué se parece a qué."""

    PALABRAS = ["garantia", "devolucion", "envio", "reembolso", "contacto", "clima", "otro"]

    def __init__(self, falla=False):
        self.falla, self.pedidos = falla, 0

    def embeber_fijos(self, textos):
        return self.embeber(textos)

    def embeber(self, textos):
        self.pedidos += 1
        if self.falla:
            raise ErrorLLM("sin red")
        out = []
        for t in textos:
            t = t.lower()
            v = [float(p in t or (p == "devolucion" and "devolver" in t) or (p == "reembolso" and "reembols" in t))
                 for p in self.PALABRAS[:-2]]
            v += [1.0 if ("clima" in t or "pelicula" in t) else 0.0, 0.01]
            out.append(v)
        return out


@pytest.fixture(scope="module")
def indice():
    return cargar_indice()


def test_las_preguntas_fuera_de_alcance_no_estan_en_la_evaluacion():
    anclas = {t.lower() for t in json.loads(FUERA_DE_ALCANCE.read_text(encoding="utf-8"))["preguntas"]}
    assert not [c["texto"] for c in cargar_casos_rag() if c["texto"].lower() in anclas]


def test_recupera_por_significado_lo_que_bm25_no_ve(indice):
    rec = RecuperadorHibrido(indice, ClienteFalso(), fuera_de_alcance=["clima de hoy"], margen=0.1)
    assert [r.fragmento.documento for r in rec.buscar("garantia")][:1] == ["garantia"]


def test_fuera_de_alcance_no_devuelve_documentos(indice):
    rec = RecuperadorHibrido(indice, ClienteFalso(), fuera_de_alcance=["clima de hoy", "pelicula"], margen=0.1)
    assert rec.buscar("clima hoy") == []


def test_si_fallan_los_embeddings_responde_bm25(indice):
    rec = RecuperadorHibrido(indice, ClienteFalso(falla=True), fuera_de_alcance=["clima"])
    r = rec.buscar("Cuánto dura la garantía de una licuadora?")
    assert rec.ultimo_respaldo is True and r[0].fragmento.documento == "garantia"


def test_los_embeddings_de_documentos_y_anclas_se_piden_una_sola_vez(indice):
    cliente = ClienteFalso()
    rec = RecuperadorHibrido(indice, cliente, fuera_de_alcance=["clima"])
    rec.buscar("garantia")
    antes = cliente.pedidos
    rec.buscar("envio")
    assert cliente.pedidos == antes + 1      # solo la consulta nueva


def test_sin_embeddings_configurados_se_usa_bm25():
    assert type(crear_recuperador(Config(proveedor="none", embedding_model=""))).__name__ == "IndiceBM25"
    assert type(crear_recuperador(Config(proveedor="openai", modelo="m", embedding_model="e"))).__name__ \
        == "RecuperadorHibrido"


def test_el_cliente_exige_un_modelo():
    with pytest.raises(ErrorLLM):
        ClienteEmbeddings(Config(proveedor="openai", embedding_model=""))


def test_conjunto_de_rag_con_bm25_sin_red(indice):
    """Piso del modo offline (BM25, el respaldo): las cifras actuales son ~79 % de recall."""
    r = medir_rag(cargar_casos_rag(), indice.buscar)
    assert r["aciertos"] / r["positivos"] >= 0.65
    assert r["rechazados"] / r["ajenos"] >= 0.85


def _ollama_disponible():
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return True
    except OSError:
        return False


@pytest.mark.skipif(os.environ.get("TIENDAHOGAR_TEST_OLLAMA") != "1" or not _ollama_disponible(),
                    reason="opt-in: TIENDAHOGAR_TEST_OLLAMA=1 y Ollama local con embeddinggemma")
def test_conjunto_de_rag_con_embeddings_reales(indice):
    config = Config(proveedor="openai", modelo="m", embedding_model="embeddinggemma",
                    base_url="http://localhost:11434/v1", timeout_s=120)
    rec = RecuperadorHibrido(indice, ClienteEmbeddings(config))
    for conjunto in ("desarrollo", "prueba"):
        r = medir_rag([c for c in cargar_casos_rag() if c["conjunto"] == conjunto], rec.buscar)
        assert r["aciertos"] / r["positivos"] >= 0.78, conjunto
        assert r["rechazados"] / r["ajenos"] >= 0.8, conjunto
