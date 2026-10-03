"""Mide la latencia del agente por etapa y separa lo que depende de los modelos de lo que depende del código.

    python -m tiendahogar.rendimiento              # con lo configurado en .env (modelo de lenguaje y embeddings)
    python -m tiendahogar.rendimiento --sin-llm    # sin modelo de lenguaje: mide la herramienta con embeddings
    python -m tiendahogar.rendimiento --offline    # sin ningún modelo: reglas, n-gramas y BM25
    python -m tiendahogar.rendimiento --sin-llm --concurrente 8   # 8 clientes a la vez sobre un mismo agente
    ... --concurrente 8 --nuevas   # además, cada pregunta es distinta (hay que pedir sus embeddings)

Cada pregunta distinta se mide una vez ("primera vez": hay que pedir sus embeddings) y otra vez ("repetida":
ya están en memoria). Antes se mide el arranque en frío: construir el agente y responder la primera pregunta.
"""

from __future__ import annotations

import os
import statistics
import sys
import time

PREGUNTAS = [
    "Cuánto dura la garantía de una licuadora?",
    "Puedo devolver un producto en liquidación?",
    "Cuánto tarda el envío a otra ciudad?",
    "Cuánto tarda un reembolso?",
    "Mi lavadora tiene 45 días y falla, la puedo devolver?",
    "Dónde está mi pedido ORD-1003?",
    "Estado del pedido 1001",
    "Ya salió lo que compré?",
    "Quiero un reembolso de $900",
    "El vendedor me trató mal",
    "Me cobraron dos veces la compra",
    "Voy a iniciar una demanda",
    "El vendedor me trató mal y además quiero saber cuánto dura la garantía de la lavadora",
    "Disputo el cobro de mi factura, y mi pedido ORD-1003 cuándo llega?",
    "Cuál es la capital de Francia?",
    "Quiero un reembolso de $500 por mi lavadora",
]


def _percentil(valores: list[float], p: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(int(round(p * (len(ordenados) - 1))), len(ordenados) - 1)]


def _resumen(nombre: str, filas: list[dict[str, float]]) -> None:
    print(f"\n{nombre}")
    print(f"{'balde':26s} {'mediana':>10s} {'p95':>10s}   (ms, {len(filas)} preguntas)")
    for clave, titulo in (("total_ms", "total"), ("modelo_generativo_ms", "modelo de lenguaje"),
                          ("modelo_embeddings_ms", "modelo de embeddings"), ("codigo_ms", "código propio"),
                          ("guardrail_ms", "  etapa: guardrail"), ("recuperacion_ms", "  etapa: recuperación"),
                          ("pedidos_ms", "  etapa: tool de pedidos"), ("intencion_ms", "  etapa: intención"),
                          ("validacion_ms", "  etapa: validación")):
        v = [f[clave] for f in filas]
        print(f"{titulo:26s} {statistics.median(v):10.1f} {_percentil(v, 0.95):10.1f}")
    llamadas = [f["embeddings_llamadas"] for f in filas]
    print(f"{'llamadas de embeddings':26s} {statistics.median(llamadas):10.1f} {max(llamadas):10.0f}   (por pregunta; mediana y máximo)")


def concurrente(agente, clientes: int, rondas: int = 5, nuevas: bool = False) -> int:
    """Varios clientes a la vez sobre un mismo agente (cada pregunta con una sesión nueva). Verifica que cada respuesta sea igual a la
    que da el agente solo y mide latencia y capacidad de la herramienta. Con modelo de lenguaje no tiene sentido (serían
    llamadas al mismo servidor local), por eso se usa con --sin-llm o --offline. Con `nuevas` cada pregunta lleva un texto
    distinto, para que haya que pedir sus embeddings al servicio (y se compara solo el estado de la respuesta)."""
    import random
    from concurrent.futures import ThreadPoolExecutor

    from .sesion import Sesion
    base = {p: (r.estado, r.texto) for p in PREGUNTAS for r in [agente.responder(p)]}       # el agente solo (y la caché tibia)
    t_sec = time.perf_counter()
    for p in PREGUNTAS * rondas:
        agente.responder(p)
    sec_s = time.perf_counter() - t_sec

    def cliente(n: int) -> tuple[list[float], list[str], list[str]]:
        rnd = random.Random(n)
        lat, distintas, errores = [], [], []
        for _ in range(rondas):
            orden = PREGUNTAS[:]
            rnd.shuffle(orden)
            for p in orden:
                sesion = Sesion()          # una conversación nueva por pregunta: lo que se compara es la respuesta sola
                texto = f"{p} (caso {n}-{len(lat)})" if nuevas else p
                t0 = time.perf_counter()
                try:
                    r = agente.responder(texto, sesion)
                except Exception as e:                                 # noqa: BLE001 - se informa, no se oculta
                    errores.append(f"{type(e).__name__}: {e}")
                    continue
                lat.append((time.perf_counter() - t0) * 1000)
                if (r.estado != base[p][0]) if nuevas else ((r.estado, r.texto) != base[p]):
                    distintas.append(p)
        return lat, distintas, errores

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=clientes) as pool:
        resultados = list(pool.map(cliente, range(clientes)))
    total_s = time.perf_counter() - t0
    lat = [x for r in resultados for x in r[0]]
    distintas = [x for r in resultados for x in r[1]]
    errores = [x for r in resultados for x in r[2]]
    print(f"\n{clientes} clientes a la vez,{rondas} rondas de {len(PREGUNTAS)} preguntas cada uno ({len(lat)} respuestas)")
    print(f"un solo cliente, en serie: {len(PREGUNTAS) * rondas / sec_s:8.0f} respuestas por segundo")
    print(f"{clientes} clientes a la vez:      {len(lat) / total_s:8.0f} respuestas por segundo")
    print(f"latencia por respuesta: mediana {statistics.median(lat):.1f} ms, p95 {_percentil(lat, 0.95):.1f} ms, máxima {max(lat):.1f} ms")
    print(f"errores: {len(errores)}   respuestas distintas a las del agente solo: {len(distintas)}")
    for e in errores[:3]:
        print("  ", e)
    return 0 if not errores and not distintas else 1


def main(argv: list[str]) -> int:
    if "--offline" in argv:
        os.environ["LLM_PROVIDER"] = "none"
    from .agent import AgenteSoporte
    from .llm import crear_llm

    llm = None if ("--sin-llm" in argv or "--offline" in argv) else crear_llm()
    t0 = time.perf_counter()
    agente = AgenteSoporte(llm=llm)
    construir_ms = (time.perf_counter() - t0) * 1000
    modo = ("offline (sin modelos)" if "--offline" in argv else
            "sin modelo de lenguaje" if llm is None else "con modelo de lenguaje")
    print(f"Modo: {modo}.  Embeddings: {'sí' if agente.cliente_embeddings else 'no'}")
    print(f"Construir el agente: {construir_ms:.0f} ms")

    if "--concurrente" in argv:
        n = int(argv[argv.index("--concurrente") + 1])
        return concurrente(agente, n, nuevas="--nuevas" in argv)

    primera = agente.responder(PREGUNTAS[0])
    print(f"Primera pregunta (arranque en frío): {primera.tiempos['total_ms']:.0f} ms "
          f"(embeddings {primera.tiempos['modelo_embeddings_ms']:.0f} ms, modelo de lenguaje "
          f"{primera.tiempos['modelo_generativo_ms']:.0f} ms, código {primera.tiempos['codigo_ms']:.0f} ms, "
          f"{primera.tiempos['embeddings_llamadas']} llamadas)")

    filas = [primera.tiempos]
    detalle = [(PREGUNTAS[0], primera)]
    for pregunta in PREGUNTAS[1:]:
        r = agente.responder(pregunta)
        filas.append(r.tiempos)
        detalle.append((pregunta, r))
    print(f"\n{'pregunta':58s} {'estado':16s} {'total':>8s} {'modelo LL':>10s} {'embeddings':>11s} {'código':>8s} {'llam':>5s}")
    for pregunta, r in detalle:
        t = r.tiempos
        print(f"{pregunta[:57]:58s} {r.estado:16s} {t['total_ms']:8.0f} {t['modelo_generativo_ms']:10.0f} "
              f"{t['modelo_embeddings_ms']:11.0f} {t['codigo_ms']:8.1f} {t['embeddings_llamadas']:5d}")
    _resumen("Primera vez que se ve cada pregunta", filas)

    repetidas = [agente.responder(p).tiempos for p in PREGUNTAS]
    _resumen("Repetidas (embeddings ya en memoria)", repetidas)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
