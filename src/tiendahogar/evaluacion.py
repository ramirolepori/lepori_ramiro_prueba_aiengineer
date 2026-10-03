"""Mide el guardrail contra el conjunto de frases de `tests/data/guardrail_evaluacion.json`.

    python -m tiendahogar.evaluacion              # guardrail: reglas, reglas + n-gramas y reglas + embeddings
    python -m tiendahogar.evaluacion pedidos      # extracción de números de pedido e intención de consulta
    python -m tiendahogar.evaluacion rag          # recuperación de documentos: BM25 contra híbrido
    python -m tiendahogar.evaluacion --barrido    # además, barre el margen sobre el conjunto de desarrollo
    python -m tiendahogar.evaluacion --fallos     # lista los casos que fallan

El conjunto se divide en `desarrollo` (se usa para ajustar el margen) y `prueba` (no se toca al ajustar y
se reporta aparte). `esperado = []` significa que la frase NO debe escalar.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from . import semantica
from .config import RAIZ, Config
from .guardrails import evaluar
from .pedidos import extraer_order_ids
from .semantica import INTENCIONES, ClasificadorSemantico, PuntajeEmbeddings, PuntajeNgramas

CASOS = RAIZ / "tests" / "data" / "guardrail_evaluacion.json"
CASOS_PEDIDOS = RAIZ / "tests" / "data" / "pedidos_evaluacion.json"
CASOS_RAG = RAIZ / "tests" / "data" / "rag_evaluacion.json"


def cargar_casos_rag(ruta: Path = CASOS_RAG) -> list[dict]:
    return json.loads(ruta.read_text(encoding="utf-8"))["casos"]


def medir_rag(casos: list[dict], buscar) -> dict:
    """Recall (se recuperan todos los documentos esperados), rechazo de lo fuera de alcance y documentos de más."""
    positivos = aciertos = ajenos = rechazados = extras = 0
    fallos: list[tuple[dict, list[str]]] = []
    for c in casos:
        obtenidos = {r.fragmento.documento for r in buscar(c["texto"])}
        esperado = set(c["esperado"])
        if esperado:
            positivos += 1
            ok = esperado <= obtenidos
            aciertos += ok
            extras += len(obtenidos - esperado)
        else:
            ajenos += 1
            ok = not obtenidos
            rechazados += ok
        if not ok:
            fallos.append((c, sorted(obtenidos)))
    return {"positivos": positivos, "aciertos": aciertos, "ajenos": ajenos, "rechazados": rechazados,
            "extras": extras, "fallos": fallos}


def _linea_rag(nombre: str, r: dict) -> str:
    return (f"{nombre:34s} recall {r['aciertos']:3d}/{r['positivos']:<3d} ({100 * r['aciertos'] / max(r['positivos'], 1):4.1f} %)"
            f"   fuera de alcance rechazadas {r['rechazados']}/{r['ajenos']}   documentos de más {r['extras']}")


def main_rag(argv: list[str]) -> int:
    from .rag import RecuperadorHibrido, cargar_indice
    from .embeddings import ClienteEmbeddings
    config = Config()
    casos = cargar_casos_rag()
    indice = cargar_indice()
    buscadores = {"BM25 solo": indice.buscar}
    if config.embedding_model and config.proveedor == "openai":
        buscadores[f"híbrido ({config.embedding_model})"] = RecuperadorHibrido(indice, ClienteEmbeddings(config)).buscar
    for nombre_conjunto in ("desarrollo", "prueba"):
        lista = [c for c in casos if c["conjunto"] == nombre_conjunto]
        print(f"\n== {nombre_conjunto} ({len(lista)} preguntas) ==")
        for nombre, buscar in buscadores.items():
            r = medir_rag(lista, buscar)
            print(_linea_rag(nombre, r))
            if "--fallos" in argv:
                for c, obtenidos in r["fallos"]:
                    print(f"     [{c['tipo']}] esperado={c['esperado']} obtenido={obtenidos} :: {c['texto'][:80]}")
    return 0


def cargar_casos(ruta: Path = CASOS) -> list[dict]:
    return [c for c in json.loads(ruta.read_text(encoding="utf-8"))["casos"] if c["esperado"] != ["inyeccion"]]


def medir(casos: list[dict], clasificador: ClasificadorSemantico | None) -> dict:
    riesgo = detectados = permitidos = falsos = 0
    fallos: list[tuple[dict, list[str]]] = []
    por_tipo: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for c in casos:
        pred = {e.categoria for e in evaluar(c["texto"], clasificador)}
        esperado = set(c["esperado"])
        if esperado:
            riesgo += 1
            ok = esperado <= pred
            detectados += ok
            por_tipo[c["tipo"]][0] += ok
            por_tipo[c["tipo"]][1] += 1
        else:
            permitidos += 1
            ok = not pred
            falsos += not ok
        if not ok:
            fallos.append((c, sorted(pred)))
    return {"riesgo": riesgo, "detectados": detectados, "permitidos": permitidos, "falsos": falsos,
            "fallos": fallos, "por_tipo": dict(por_tipo)}


def cargar_casos_pedidos(ruta: Path = CASOS_PEDIDOS) -> list[dict]:
    return json.loads(ruta.read_text(encoding="utf-8"))["casos"]


def medir_pedidos(casos: list[dict], clasificador: ClasificadorSemantico) -> dict:
    """Extracción exacta de los números y reconocimiento de la intención de consultar un pedido sin darlo."""
    from .agent import AgenteSoporte
    agente = AgenteSoporte(clasificador=clasificador)
    ids_ok = intencion_ok = con_intencion = sin_intencion = falsos = 0
    fallos: list[tuple[dict, str]] = []
    for c in casos:
        got = extraer_order_ids(c["texto"])
        if got == c["ids"]:
            ids_ok += 1
        else:
            fallos.append((c, f"ids={got}"))
        if not c["ids"]:                       # sin número: se mide la intención
            detectada = agente._consulta_de_pedido(c["texto"])
            if c["intencion"]:
                con_intencion += 1
                intencion_ok += detectada
                if not detectada:
                    fallos.append((c, "no reconoció la consulta de pedido"))
            else:
                sin_intencion += 1
                if detectada:
                    falsos += 1
                    fallos.append((c, "creyó que consultaba un pedido"))
    return {"total": len(casos), "ids_ok": ids_ok, "con_intencion": con_intencion, "intencion_ok": intencion_ok,
            "sin_intencion": sin_intencion, "falsos": falsos, "fallos": fallos}


def _linea_pedidos(nombre: str, r: dict) -> str:
    return (f"{nombre:34s} números {r['ids_ok']}/{r['total']}   intención {r['intencion_ok']}/{r['con_intencion']}"
            f"   falsos positivos {r['falsos']}/{r['sin_intencion']}")


def _linea(nombre: str, r: dict) -> str:
    return (f"{nombre:34s} riesgo {r['detectados']:3d}/{r['riesgo']:<3d} ({100 * r['detectados'] / max(r['riesgo'], 1):4.1f} %)"
            f"   falsos positivos {r['falsos']}/{r['permitidos']}")


def _clasificadores(config: Config, margen: float | None = None) -> dict[str, ClasificadorSemantico | None]:
    out: dict[str, ClasificadorSemantico | None] = {
        "solo reglas": None,
        "reglas + n-gramas": ClasificadorSemantico(None, PuntajeNgramas()),
    }
    if config.embedding_model and config.proveedor == "openai":
        out[f"reglas + {config.embedding_model}"] = ClasificadorSemantico(
            PuntajeEmbeddings(config), PuntajeNgramas(), margen=margen)
    return out


def main_pedidos(argv: list[str]) -> int:
    config = Config()
    casos = cargar_casos_pedidos()
    clasificadores = {k: v for k, v in _clasificadores(config).items() if v is not None}
    for nombre_conjunto in ("desarrollo", "prueba"):
        lista = [c for c in casos if c["conjunto"] == nombre_conjunto]
        print(f"\n== {nombre_conjunto} ({len(lista)} frases) ==")
        for nombre, clf in clasificadores.items():
            r = medir_pedidos(lista, clf)
            print(_linea_pedidos(nombre, r))
            if "--fallos" in argv:
                for c, motivo in r["fallos"]:
                    print(f"     [{c['tipo']}] {motivo} :: {c['texto'][:80]}")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "pedidos":
        return main_pedidos(argv[1:])
    if argv and argv[0] == "rag":
        return main_rag(argv[1:])
    config = Config()
    casos = cargar_casos()
    conjuntos = {"desarrollo": [c for c in casos if c["conjunto"] == "desarrollo"],
                 "prueba": [c for c in casos if c["conjunto"] == "prueba"]}
    clasificadores = _clasificadores(config)
    for nombre_conjunto, lista in conjuntos.items():
        print(f"\n== {nombre_conjunto} ({len(lista)} frases) ==")
        for nombre, clf in clasificadores.items():
            r = medir(lista, clf)
            print(_linea(nombre, r))
            if "--fallos" in argv:
                for c, pred in r["fallos"]:
                    print(f"     [{c['tipo']}] esperado={c['esperado']} obtenido={pred} :: {c['texto'][:80]}")
    if "--barrido" in argv:
        for nombre, clf in clasificadores.items():
            if clf is None or clf.principal is None:
                continue
            print(f"\n== barrido de margen sobre desarrollo: {nombre} ==")
            for margen in (0.0, 0.02, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10, 0.12):
                clf.margen = margen
                print(_linea(f"margen {margen:.2f}", medir(conjuntos["desarrollo"], clf)))
            clf.margen = semantica.MARGEN_EMBEDDINGS
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
