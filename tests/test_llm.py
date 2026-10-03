"""Prueba los clientes de LLM contra un servidor HTTP local que imita las APIs (sin red ni claves)."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tiendahogar import AgenteSoporte
from tiendahogar.config import Config
from tiendahogar.llm import Anthropic, ErrorLLM, OpenAICompatible, crear_llm


class Servidor:
    def __init__(self, manejar):
        self.pedidos: list[dict] = []
        servidor = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                servidor.pedidos.append({"ruta": self.path, "cab": dict(self.headers), "cuerpo": cuerpo})
                codigo, resp = manejar(cuerpo)
                datos = json.dumps(resp).encode()
                self.send_response(codigo)
                self.send_header("Content-Length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def log_message(self, *a):
                pass

        self.http = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def cerrar(self):
        self.http.shutdown()


def config(url, proveedor="openai", **kw):
    return Config(proveedor=proveedor, modelo="m", api_key="clave-de-prueba", base_url=url, timeout_s=5, **kw)


OK_OPENAI = {"choices": [{"message": {"content": " La garantía de una lavadora es de 12 meses. "}}]}
RESPUESTA = "La garantía de una lavadora es de 12 meses."


def test_openai_compatible_arma_el_pedido_y_lee_la_respuesta():
    s = Servidor(lambda c: (200, OK_OPENAI))
    try:
        assert OpenAICompatible(config(s.url + "/v1")).generar("sistema", "pregunta") == RESPUESTA
        p = s.pedidos[0]
        assert p["ruta"] == "/v1/chat/completions" and p["cab"]["Authorization"] == "Bearer clave-de-prueba"
        assert p["cuerpo"]["messages"][0] == {"role": "system", "content": "sistema"}
        assert p["cuerpo"]["max_tokens"] == 1024
    finally:
        s.cerrar()


def test_openai_reintenta_con_max_completion_tokens_si_rechaza_max_tokens():
    def manejar(c):
        if "max_tokens" in c or "temperature" in c:
            return 400, {"error": {"message": "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens'."}}
        return 200, OK_OPENAI

    s = Servidor(manejar)
    try:
        assert OpenAICompatible(config(s.url)).generar("s", "p") == RESPUESTA
        assert len(s.pedidos) == 2 and "max_completion_tokens" in s.pedidos[1]["cuerpo"]
    finally:
        s.cerrar()


def test_un_400_que_no_se_arregla_se_informa():
    s = Servidor(lambda c: (400, {"error": {"message": "modelo inexistente"}}))
    try:
        with pytest.raises(ErrorLLM, match="modelo inexistente"):
            OpenAICompatible(config(s.url)).generar("s", "p")
    finally:
        s.cerrar()


def test_clave_invalida_no_se_reintenta():
    s = Servidor(lambda c: (401, {"error": "no autorizado"}))
    try:
        with pytest.raises(ErrorLLM, match="401"):
            OpenAICompatible(config(s.url)).generar("s", "p")
        assert len(s.pedidos) == 1
    finally:
        s.cerrar()


def test_conexion_cortada_sin_respuesta_es_un_error_controlado(monkeypatch):
    import socket

    monkeypatch.setattr("tiendahogar.llm.time.sleep", lambda s: None)
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()

    def cortar():
        while True:
            try:
                srv.accept()[0].close()      # cierra sin responder, como Ollama cuando se cae el modelo
            except OSError:
                return

    threading.Thread(target=cortar, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.getsockname()[1]}"
        with pytest.raises(ErrorLLM, match="no se pudo llamar"):
            OpenAICompatible(config(url)).generar("s", "p")
    finally:
        srv.close()


def test_anthropic_arma_el_pedido_y_lee_la_respuesta():
    s = Servidor(lambda c: (200, {"content": [{"type": "text", "text": "Son 6 meses."}]}))
    try:
        import tiendahogar.llm as llm
        original = llm._post
        llm._post = lambda url, cab, cuerpo, t, reintentos=2: original(s.url + "/v1/messages", cab, cuerpo, t, reintentos)
        try:
            assert Anthropic(config(s.url, "anthropic")).generar("sistema", "pregunta") == "Son 6 meses."
        finally:
            llm._post = original
        p = s.pedidos[0]
        cab = {k.lower(): v for k, v in p["cab"].items()}
        assert cab["x-api-key"] == "clave-de-prueba" and p["cuerpo"]["system"] == "sistema"
    finally:
        s.cerrar()


def test_agente_con_proveedor_openai_de_punta_a_punta():
    s = Servidor(lambda c: (200, OK_OPENAI))
    try:
        agente = AgenteSoporte(llm=crear_llm(config(s.url)))
        r = agente.responder("Cuánto dura la garantía de una lavadora?")
        assert r.texto == RESPUESTA + " [garantia]"
        assert "[garantia]" in s.pedidos[0]["cuerpo"]["messages"][1]["content"]
    finally:
        s.cerrar()


def test_proveedor_desconocido_o_sin_modelo():
    with pytest.raises(ErrorLLM):
        crear_llm(Config(proveedor="otro"))
    with pytest.raises(ErrorLLM, match="LLM_MODEL"):
        crear_llm(Config(proveedor="openai", modelo=""))
    assert crear_llm(Config(proveedor="none")) is None
