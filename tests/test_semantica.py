import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tiendahogar.config import Config
from tiendahogar.evaluacion import cargar_casos, medir
from tiendahogar.guardrails import evaluar
from tiendahogar.llm import ErrorLLM
from tiendahogar.semantica import (CATEGORIAS, INTENCIONES, ClasificadorSemantico, PuntajeEmbeddings, PuntajeNgramas,
                                   cargar_anclas, crear_clasificador, segmentar)

R, T, F, L = CATEGORIAS


# --- segmentación --------------------------------------------------------------------------------------

def test_segmentar_separa_la_parte_permitida():
    unidades = segmentar("El vendedor me trató mal y además quiero saber cuánto dura la garantía")
    assert unidades[0].startswith("El vendedor me trató mal y además")      # el texto completo siempre va
    assert "El vendedor me trató mal" in unidades
    assert "quiero saber cuánto dura la garantía" in unidades


def test_segmentar_por_puntuacion():
    assert segmentar("Un empleado me faltó el respeto. Puedo devolver una licuadora usada?")[1:] == [
        "Un empleado me faltó el respeto", "Puedo devolver una licuadora usada"]


def test_segmentar_texto_corto_queda_entero():
    assert segmentar("Hola") == ["Hola"]


# --- n-gramas (respaldo offline) -----------------------------------------------------------------------

@pytest.fixture(scope="module")
def ngramas():
    return ClasificadorSemantico(None, PuntajeNgramas())


@pytest.mark.parametrize("texto,categoria", [
    ("kiero poner una keja contra un empleado", T),
    ("no reconosco este cobro en mi tarjeta", F),
    ("los boy a denunsiar", L),
    ("boy a tomar acciones lejales", L),
    ("ME ATENDIERON PESIMO EN LA TIENDA", T),
])
def test_ngramas_toleran_faltas_y_mayusculas(ngramas, texto, categoria):
    assert categoria in ngramas.detectar(texto)


def test_ngramas_no_se_activan_con_preguntas_normales(ngramas):
    for texto in ["Cuánto dura la garantía de una licuadora?", "Dónde está mi pedido ORD-1001?", "Hola"]:
        assert ngramas.detectar(texto) == {}


def test_las_anclas_cubren_las_cuatro_categorias_y_lo_permitido():
    assert set(cargar_anclas()) == {*CATEGORIAS, *INTENCIONES, "permitida"}


# --- guardrail combinado -------------------------------------------------------------------------------

class Falso:
    """Clasificador que devuelve lo que se le indique."""

    nombre = "Falso"
    ultimo_respaldo = False

    def __init__(self, resultado):
        self.resultado = resultado

    def detectar(self, texto):
        return self.resultado


def test_la_capa_semantica_suma_categorias_a_las_reglas():
    res = evaluar("una persona me hizo sentir un estorbo en la sucursal", Falso({T: 0.2}))
    assert [(e.categoria, e.origen) for e in res] == [(T, "semantica")]


def test_reembolso_semantico_exige_monto_mayor_a_500():
    assert evaluar("quiero lo que pagué de vuelta", Falso({R: 0.2})) == []
    assert evaluar("quiero lo que pagué de vuelta, fueron $500", Falso({R: 0.2})) == []
    res = evaluar("quiero lo que pagué de vuelta, fueron $900", Falso({R: 0.2}))
    assert [(e.categoria, e.origen) for e in res] == [(R, "semantica")]


def test_las_reglas_no_se_duplican_con_la_capa_semantica():
    res = evaluar("Voy a iniciar una demanda", Falso({L: 0.3}))
    assert [(e.categoria, e.origen) for e in res] == [(L, "regla")]


@pytest.mark.parametrize("texto,escala", [
    ("Con quién hablo si tengo un tema legal?", False),
    ("A dónde escribo para presentar una queja?", False),
    ("Voy a demandarlos, con quién hablo?", True),
])
def test_consulta_del_canal_se_responde_y_no_se_deriva(texto, escala):
    assert bool(evaluar(texto)) is escala


# --- respaldo y embeddings ------------------------------------------------------------------------------

class Roto:
    def puntuar(self, textos):
        raise ErrorLLM("sin red")


def test_si_fallan_los_embeddings_se_usan_los_ngramas():
    clf = ClasificadorSemantico(Roto(), PuntajeNgramas())
    assert T in clf.detectar("kiero poner una keja contra un empleado")
    assert clf.ultimo_respaldo is True


def test_sin_respaldo_el_error_sube():
    with pytest.raises(ErrorLLM):
        ClasificadorSemantico(Roto(), None).detectar("hola buenas")


class ServidorEmbeddings:
    """Imita /v1/embeddings: el vector de un texto es su bolsa de letras, así textos parecidos quedan cerca."""

    def __init__(self):
        self.pedidos = []
        yo = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                yo.pedidos.append((self.path, cuerpo))
                datos = [{"index": i, "embedding": [t.lower().count(c) for c in "abcdefghijklmnopqrstuvwxyz"]}
                         for i, t in enumerate(cuerpo["input"])]
                resp = json.dumps({"data": list(reversed(datos))}).encode()   # desordenado a propósito
                self.send_response(200)
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, *a):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.http.server_port}/v1"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()


def test_embeddings_usa_el_endpoint_y_respeta_el_orden():
    srv = ServidorEmbeddings()
    try:
        config = Config(proveedor="openai", modelo="m", embedding_model="emb", base_url=srv.url, timeout_s=5)
        anclas = {T: ["aaa bbb"], F: ["zzz yyy"], L: ["mmm nnn"], R: ["qqq rrr"], "permitida": ["ccc ddd"]}
        p = PuntajeEmbeddings(config, anclas)
        puntajes = p.puntuar(["aaa bbb", "zzz yyy"])
        assert puntajes[0][T] == pytest.approx(1.0) and puntajes[1][F] == pytest.approx(1.0)
        assert puntajes[0][T] > puntajes[0][F]
        ruta, cuerpo = srv.pedidos[0]
        assert ruta == "/v1/embeddings" and cuerpo["model"] == "emb"
        n = len(srv.pedidos)
        p.puntuar(["aaa bbb"])             # ya está en memoria: no vuelve a pedir
        assert len(srv.pedidos) == n
    finally:
        srv.http.shutdown()


def test_crear_clasificador_sin_embeddings_usa_solo_ngramas():
    clf = crear_clasificador(Config(proveedor="none", embedding_model=""))
    assert clf.principal is None and clf.nombre == "PuntajeNgramas"
    assert type(crear_clasificador(Config(proveedor="openai", modelo="m", embedding_model="e")).principal) \
        is PuntajeEmbeddings


# --- el conjunto de evaluación, sin red -----------------------------------------------------------------

def test_conjunto_de_evaluacion_con_reglas_y_ngramas():
    """Piso de calidad del modo offline. Las cifras actuales son ~80 % de detección con ≤ 1 falso positivo
    por cada 20 frases permitidas; los pisos dejan margen para no romperse con cambios menores."""
    casos = cargar_casos()
    r = medir(casos, ClasificadorSemantico(None, PuntajeNgramas()))
    assert r["detectados"] / r["riesgo"] >= 0.75
    assert r["falsos"] / r["permitidos"] <= 0.06


def test_las_reglas_solas_no_tienen_falsos_positivos_en_lo_permitido():
    r = medir(cargar_casos(), None)
    assert r["falsos"] == 0


def _ollama_disponible():
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return True
    except OSError:
        return False


@pytest.mark.skipif(os.environ.get("TIENDAHOGAR_TEST_OLLAMA") != "1" or not _ollama_disponible(),
                    reason="opt-in: TIENDAHOGAR_TEST_OLLAMA=1 y Ollama local con embeddinggemma")
def test_conjunto_de_evaluacion_con_embeddings_reales():
    """Opt-in (tarda unos minutos): es la medición con embeddings reales que se reporta en SUBMISSION.md."""
    config = Config(proveedor="openai", modelo="m", embedding_model="embeddinggemma",
                    base_url="http://localhost:11434/v1", timeout_s=120)
    clf = ClasificadorSemantico(PuntajeEmbeddings(config), PuntajeNgramas())
    for conjunto in ("desarrollo", "prueba"):
        r = medir([c for c in cargar_casos() if c["conjunto"] == conjunto], clf)
        assert r["detectados"] / r["riesgo"] >= 0.95, conjunto
        assert r["falsos"] / r["permitidos"] <= 0.10, conjunto


@pytest.mark.parametrize("texto", [
    "Quiero un rembolso de $900", "Necesito el reembolzo de 900 dolares", "Quiero el reenbolso de $900",
    "Kiero q me debuelvan $800", "Devulevan me los $600 de la lavadora", "reebolso de 1200 dolares porfa",
    "reimbolso de $1000", "me ayudan con el rembolso, pagué $900",
])
def test_reembolso_alto_con_faltas_de_ortografia_lo_detectan_las_reglas(texto):
    assert [e.categoria for e in evaluar(texto)] == [R]


def test_reembolso_con_faltas_pero_sin_monto_alto_no_escala():
    assert evaluar("Quiero un rembolso de $300") == []
    assert evaluar("Cuanto tarda el rembolso?") == []
