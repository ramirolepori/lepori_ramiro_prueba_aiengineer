"""Rendimiento: tiempos por etapa, separación entre modelos y código, y llamadas evitadas."""

import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.config import Config
from tiendahogar.embeddings import ClienteEmbeddings
from tiendahogar.rag import RecuperadorHibrido, cargar_indice
from tiendahogar.semantica import ClasificadorSemantico, PuntajeEmbeddings, PuntajeNgramas
from tiendahogar.tiempos import Cronometro, activar, etapa


class ServidorEmbeddings:
    """Imita /v1/embeddings y cuenta las llamadas: el vector de un texto es su bolsa de letras."""

    def __init__(self):
        self.llamadas = 0
        yo = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                yo.llamadas += 1
                datos = [{"index": i, "embedding": [t.lower().count(c) + 0.1 for c in "abcdefghijklmnopqrstuvwxyz"]}
                         for i, t in enumerate(cuerpo["input"])]
                resp = json.dumps({"data": datos}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, *a):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.http.server_port}/v1"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def config(self):
        return Config(proveedor="openai", modelo="m", embedding_model="emb", base_url=self.url, timeout_s=10)


@pytest.fixture()
def servidor():
    s = ServidorEmbeddings()
    yield s
    s.http.shutdown()


def agente_con_embeddings(servidor, llm=None):
    config = servidor.config()
    cliente = ClienteEmbeddings(config)
    ag = AgenteSoporte(indice=RecuperadorHibrido(cargar_indice(), cliente), llm=llm,
                       clasificador=ClasificadorSemantico(PuntajeEmbeddings(config, cliente=cliente), PuntajeNgramas()))
    ag.cliente_embeddings = cliente
    return ag


# --- cronómetro y baldes ---------------------------------------------------------------------------------

def test_el_cronometro_suma_las_etapas():
    cron = Cronometro()
    with activar(cron):
        with etapa("guardrail"):
            time.sleep(0.02)
        with etapa("guardrail"):
            time.sleep(0.02)
    assert cron.ms["guardrail"] >= 35


def test_sin_cronometro_activo_no_hace_nada():
    with etapa("guardrail"):
        pass


class LLMLento:
    def generar(self, sistema, usuario):
        time.sleep(0.15)
        return "La garantía de una licuadora es de 6 meses para electrodomésticos pequeños [garantia]."


def test_los_tiempos_separan_modelo_y_codigo():
    r = AgenteSoporte(llm=LLMLento()).responder("Cuánto dura la garantía de una licuadora?")
    t = r.tiempos
    assert t["modelo_generativo_ms"] >= 140 and t["generacion_ms"] == t["modelo_generativo_ms"]
    assert t["codigo_ms"] < t["modelo_generativo_ms"]
    assert t["total_ms"] >= t["modelo_generativo_ms"] + t["modelo_embeddings_ms"]
    assert abs(t["total_ms"] - (t["modelo_generativo_ms"] + t["modelo_embeddings_ms"] + t["codigo_ms"])) < 1


def test_sin_modelos_todo_es_codigo_y_es_rapido():
    r = AgenteSoporte().responder("Cuánto dura la garantía de una licuadora?")
    assert r.tiempos["modelo_generativo_ms"] == 0 and r.tiempos["modelo_embeddings_ms"] == 0
    assert r.tiempos["codigo_ms"] < 250        # holgado: en la práctica son unos pocos milisegundos


def test_los_tiempos_quedan_en_la_traza():
    r = AgenteSoporte().responder("Hola")
    assert r.traza[-1]["tipo"] == "fin" and "codigo_ms" in r.traza[-1]["tiempos"]


# --- llamadas evitadas ------------------------------------------------------------------------------------

def test_una_pregunta_normal_hace_una_sola_llamada_de_embeddings(servidor):
    ag = agente_con_embeddings(servidor)
    ag.responder("Cuánto dura la garantía de una licuadora?")        # arranque en frío: documentos y anclas
    antes = servidor.llamadas
    r = ag.responder("Cuánto tarda el envío a otra ciudad?")
    assert servidor.llamadas - antes == 1 and r.tiempos["embeddings_llamadas"] == 1


def test_la_misma_pregunta_no_vuelve_a_pedir_embeddings(servidor):
    ag = agente_con_embeddings(servidor)
    ag.responder("Cuánto dura la garantía de una licuadora?")
    antes = servidor.llamadas
    r = ag.responder("Cuánto dura la garantía de una licuadora?")
    assert servidor.llamadas == antes and r.tiempos["embeddings_llamadas"] == 0


def test_si_las_reglas_ya_derivan_no_se_consulta_el_modelo_de_embeddings(servidor):
    ag = agente_con_embeddings(servidor)
    ag.responder("Cuánto dura la garantía de una licuadora?")        # arranque en frío
    antes = servidor.llamadas
    r = ag.responder("Voy a iniciar una demanda")
    assert r.estado == "escalado" and servidor.llamadas == antes


def test_con_un_pedido_en_el_texto_no_se_evalua_la_intencion(servidor):
    ag = agente_con_embeddings(servidor)
    r = ag.responder("Dónde está mi pedido ORD-1003?")
    assert r.tiempos["intencion_ms"] < 1      # con el número a la vista no hay nada que preguntarle al modelo


# --- caché de embeddings de textos fijos -------------------------------------------------------------------

def test_los_vectores_son_unitarios(servidor):
    cliente = ClienteEmbeddings(servidor.config())
    for v in cliente.embeber(["garantía", "devolución de dinero"]):
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-9)


def test_la_cache_en_disco_evita_pedir_los_textos_fijos_otra_vez(servidor, tmp_path):
    fijos = ["texto fijo uno", "texto fijo dos"]
    ClienteEmbeddings(servidor.config(), cache_dir=tmp_path).embeber_fijos(fijos)
    assert servidor.llamadas == 1
    otro = ClienteEmbeddings(servidor.config(), cache_dir=tmp_path)       # otro proceso
    otro.embeber_fijos(fijos)
    assert servidor.llamadas == 1 and otro.desde_disco == 2 and otro.llamadas == 0


def test_la_cache_nunca_guarda_preguntas_de_clientes(servidor, tmp_path):
    cliente = ClienteEmbeddings(servidor.config(), cache_dir=tmp_path)
    cliente.embeber_fijos(["texto fijo"])
    cliente.embeber(["mi pregunta privada sobre un pedido"])
    guardado = next(tmp_path.glob("embeddings_*.json")).read_text(encoding="utf-8")
    assert len(json.loads(guardado)) == 1


def test_una_cache_danada_se_ignora(servidor, tmp_path):
    cliente = ClienteEmbeddings(servidor.config(), cache_dir=tmp_path)
    (tmp_path / "embeddings_v2_emb.json").write_text("{esto no es json", encoding="utf-8")
    assert len(cliente.embeber_fijos(["texto fijo"])) == 1 and servidor.llamadas == 1


def test_sin_cache_configurada_no_se_escribe_nada(servidor, tmp_path):
    cliente = ClienteEmbeddings(servidor.config(), cache_dir=None)
    cliente.embeber_fijos(["texto fijo"])
    assert list(tmp_path.iterdir()) == []


# --- servidor local: localhost contra 127.0.0.1 ------------------------------------------------------------

def test_localhost_se_cambia_por_ipv4():
    from tiendahogar.llm import _preferir_ipv4
    assert _preferir_ipv4("http://localhost:11434/v1") == "http://127.0.0.1:11434/v1"
    assert _preferir_ipv4("http://localhost/v1") == "http://127.0.0.1/v1"
    assert _preferir_ipv4("https://api.openai.com/v1") == "https://api.openai.com/v1"
    assert _preferir_ipv4("http://127.0.0.1:11434/v1") == "http://127.0.0.1:11434/v1"
    assert _preferir_ipv4("http://miservidor.local:8000/v1") == "http://miservidor.local:8000/v1"


def test_una_url_con_localhost_llega_al_servidor_ipv4(servidor):
    config = servidor.config()
    config.base_url = servidor.url.replace("127.0.0.1", "localhost")
    assert len(ClienteEmbeddings(config).embeber(["hola"])) == 1 and servidor.llamadas == 1
