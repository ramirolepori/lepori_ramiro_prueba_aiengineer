"""Varias consultas a la vez sobre un mismo agente: mismas respuestas que en serie, sin errores y con trazas íntegras."""

import json
from concurrent.futures import ThreadPoolExecutor

from tiendahogar import AgenteSoporte
from tiendahogar.rendimiento import PREGUNTAS
from tiendahogar.sesion import Sesion


def test_las_respuestas_en_paralelo_son_las_mismas_que_en_serie():
    agente = AgenteSoporte()
    esperado = {p: (r.estado, r.texto) for p in PREGUNTAS for r in [agente.responder(p)]}

    def cliente(n: int) -> list[tuple[str, tuple[str, str]]]:
        salida = []
        for p in PREGUNTAS[n % 4:] + PREGUNTAS[:n % 4]:
            r = agente.responder(p, Sesion())          # una conversación nueva por pregunta
            salida.append((p, (r.estado, r.texto)))
        return salida

    with ThreadPoolExecutor(max_workers=12) as pool:
        resultados = [x for r in pool.map(cliente, range(24)) for x in r]
    assert len(resultados) == 24 * len(PREGUNTAS)
    assert all(esperado[p] == r for p, r in resultados)


def test_las_sesiones_no_se_mezclan_entre_hilos():
    agente = AgenteSoporte()

    def conversacion(n: int) -> str:
        s = Sesion()
        agente.responder("Quiero un reembolso de la heladera", s)
        return agente.responder(f"fueron {400 + 100 * (n % 2)}", s).estado
    # 400 y 500 no superan $500: ninguna conversación puede terminar derivada por otra
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(conversacion, range(32))) == {"respondido"}

    def conversacion_alta(n: int) -> str:
        s = Sesion()
        agente.responder("Quiero un reembolso de la heladera", s)
        return agente.responder("fueron 900", s).estado
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(conversacion_alta, range(32))) == {"escalado"}


def test_las_trazas_en_paralelo_quedan_completas(tmp_path):
    agente = AgenteSoporte(trazas_dir=tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        respuestas = list(pool.map(agente.responder, PREGUNTAS * 3))
    lineas = (tmp_path / "trazas.jsonl").read_text(encoding="utf-8").splitlines()
    eventos = [json.loads(linea) for linea in lineas]                 # ninguna línea quedó cortada o mezclada
    assert len(eventos) == sum(len(r.traza) for r in respuestas)
    por_traza: dict[str, list[str]] = {}
    for e in eventos:
        por_traza.setdefault(e["traza"], []).append(e["tipo"])
    assert len(por_traza) == len(respuestas) and all(t[0] == "entrada" and t[-1] == "fin" for t in por_traza.values())
