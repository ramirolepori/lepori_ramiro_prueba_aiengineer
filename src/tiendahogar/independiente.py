"""Conjunto de evaluación independiente: frases escritas por una persona que NO escribió el código ni las anclas.

Las frases originales (`origen = "Ramiro"`) se congelan y se miden sin ajustar nada a partir de ellas. Las variantes
(`origen = "variante"`) se derivan de una original (ruido automático o paráfrasis) y se reportan aparte, porque
dependen de la redacción de su original y no son tan independientes.

    python -m tiendahogar.independiente importar frases.txt     # lee las frases pegadas y arma tests/data/independiente.json
    python -m tiendahogar.independiente variantes               # suma variantes automáticas (sin tildes, mayúsculas, errores)
    python -m tiendahogar.independiente medir [--fallos]        # mide guardrail, pedidos y RAG, por origen

Formato de cada línea (las que empiezan con # y las vacías se ignoran):    CÓDIGO | frase

    R            reembolso de más de $500 (debe derivarse)       T   queja por el trato de un empleado
    F            disputa de facturación                          L   tema legal
    T+F          varias a la vez                                 OK  no debe derivarse
    P            pregunta por un pedido sin dar el número        P=1001 o P=ORD-1001,1004   da el número
    NP           menciona números o "pedido" pero no consulta un estado
    D=garantia   pregunta de política: documento esperado (garantia, devoluciones, envios, reembolsos, contacto)
    D=garantia+devoluciones   dos documentos          X   fuera de alcance: ningún documento sirve

Toda frase P, NP, D o X se mide además como "no debe derivarse". Una tercera columna opcional (`| 12`) indica de qué
frase original deriva una variante.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata

from .config import RAIZ, Config
from .evaluacion import (_clasificadores, _linea, _linea_pedidos, _linea_rag, medir, medir_pedidos, medir_rag)

ARCHIVO = RAIZ / "tests" / "data" / "independiente.json"
CATEGORIAS = {"R": "reembolso_mayor_500", "T": "queja_trato", "F": "disputa_facturacion", "L": "tema_legal"}
DOCUMENTOS = {"garantia", "devoluciones", "envios", "reembolsos", "contacto"}


def interpretar_codigo(codigo: str) -> dict:
    """Traduce un código a lo que se espera de la frase. Lanza ValueError si no lo entiende."""
    c = codigo.strip()
    if c.upper() == "OK":
        return {"grupo": "guardrail", "esperado_guardrail": []}
    if re.fullmatch(r"[RTFL](\+[RTFL])*", c.upper()):
        return {"grupo": "guardrail", "esperado_guardrail": [CATEGORIAS[x] for x in c.upper().split("+")]}
    if c.upper() == "P":
        return {"grupo": "pedido", "esperado_guardrail": [], "ids": [], "intencion": True}
    if c.upper() == "NP":
        return {"grupo": "pedido", "esperado_guardrail": [], "ids": [], "intencion": False}
    m = re.fullmatch(r"P=(.+)", c, re.IGNORECASE)
    if m:
        ids = [f"ORD-{n}" for n in re.findall(r"\d{3,8}", m.group(1))]
        if not ids:
            raise ValueError(f"código de pedido sin números: {codigo!r}")
        return {"grupo": "pedido", "esperado_guardrail": [], "ids": ids, "intencion": True}
    if c.upper() == "X":
        return {"grupo": "rag", "esperado_guardrail": [], "esperado_docs": []}
    m = re.fullmatch(r"d=([a-z+]+)", c.lower())
    if m:
        docs = m.group(1).split("+")
        malos = [d for d in docs if d not in DOCUMENTOS]
        if malos:
            raise ValueError(f"documento desconocido {malos} (usar {sorted(DOCUMENTOS)})")
        return {"grupo": "rag", "esperado_guardrail": [], "esperado_docs": docs}
    raise ValueError(f"código desconocido: {codigo!r}")


def leer_frases(texto: str) -> list[dict]:
    """Interpreta las líneas `CÓDIGO | frase [| base]`. Devuelve registros sin id."""
    registros: list[dict] = []
    for n, linea in enumerate(texto.splitlines(), 1):
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        partes = [p.strip() for p in linea.split("|")]
        if len(partes) < 2 or not partes[1]:
            raise ValueError(f"línea {n}: falta el código o la frase: {linea!r}")
        try:
            registro = {"texto": partes[1], "codigo": partes[0], **interpretar_codigo(partes[0])}
        except ValueError as e:
            raise ValueError(f"línea {n}: {e}") from e
        if len(partes) > 2 and partes[2]:
            registro["base"] = partes[2]
        registros.append(registro)
    return registros


# --- variantes automáticas (conservan lo que se espera de la frase original) ------------------------------------

def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _con_error(t: str) -> str:
    """Un error de tipeo determinístico en la palabra de letras más larga (sin tocar números ni ORD)."""
    palabras = [m for m in re.finditer(r"[A-Za-záéíóúñÁÉÍÓÚÑ]{6,}", t) if m.group(0).upper() != "ORD"]
    if not palabras:
        return t
    m = max(palabras, key=lambda x: (len(x.group(0)), -x.start()))
    w = m.group(0)
    medio = len(w) // 2
    roto = w[:medio] + w[medio + 1] + w[medio] + w[medio + 2:] if medio + 2 < len(w) else w[:-1]
    return t[:m.start()] + roto + t[m.end():]


def _estilo_chat(t: str) -> str:
    """Sin tildes, sin signos y en minúsculas. Los puntos y comas dentro de un número (1.200, 500,50) se conservan."""
    return re.sub(r"[¿¡?!]|(?<!\d)[.,;:]|[.,;:](?!\d)", "", _sin_tildes(t)).lower()


def variantes_automaticas(texto: str) -> dict[str, str]:
    out = {"sin_tildes": _sin_tildes(texto), "mayusculas": texto.upper(), "con_error": _con_error(texto),
           "estilo_chat": _estilo_chat(texto)}
    return {k: v for k, v in out.items() if v != texto}


# --- archivo -------------------------------------------------------------------------------------------------------

def cargar(ruta=ARCHIVO) -> list[dict]:
    return json.loads(ruta.read_text(encoding="utf-8"))["casos"] if ruta.exists() else []


def guardar(casos: list[dict], ruta=ARCHIVO) -> None:
    ruta.write_text(json.dumps({
        "descripcion": "Frases escritas por Ramiro (origen 'Ramiro', congeladas) y variantes derivadas (origen 'variante'). "
                       "No se ajusta ningún umbral ni ancla a partir de las originales.",
        "casos": casos}, ensure_ascii=False, indent=2), encoding="utf-8")


def importar(texto: str, ruta=ARCHIVO) -> list[dict]:
    """Reemplaza las frases originales por las del texto (y descarta las variantes, que hay que regenerar)."""
    casos = []
    for i, r in enumerate(leer_frases(texto), 1):
        casos.append({"id": f"i{i:03d}", "origen": "Ramiro", **r})
    guardar(casos, ruta)
    return casos


def agregar_variantes(ruta=ARCHIVO, manuales: str = "") -> list[dict]:
    casos = [c for c in cargar(ruta) if c["origen"] == "Ramiro"]
    originales = {c["id"]: c for c in casos}
    nuevos: list[dict] = []
    for c in casos:
        for nombre, texto in variantes_automaticas(c["texto"]).items():
            nuevos.append({**{k: v for k, v in c.items() if k not in {"id", "texto", "origen"}},
                           "id": f"{c['id']}-{nombre}", "texto": texto, "origen": "variante", "base": c["id"],
                           "variante": nombre})
    for r in leer_frases(manuales) if manuales else []:
        base = originales.get(f"i{int(r['base']):03d}") if str(r.get("base", "")).isdigit() else None
        nuevos.append({**r, "id": f"{base['id'] if base else 'manual'}-m{len(nuevos)}", "origen": "variante",
                       "base": base["id"] if base else None, "variante": "parafrasis"})
    guardar(casos + nuevos, ruta)
    return nuevos


# --- medición ------------------------------------------------------------------------------------------------------

def medir_origen(casos: list[dict], config: Config, fallos: bool = False) -> None:
    from .embeddings import ClienteEmbeddings
    from .rag import RecuperadorHibrido, cargar_indice
    gr = [{"texto": c["texto"], "esperado": c["esperado_guardrail"], "tipo": c["origen"]} for c in casos]
    pe = [{"texto": c["texto"], "ids": c["ids"], "intencion": c["intencion"], "tipo": c["origen"]}
          for c in casos if c["grupo"] == "pedido"]
    ra = [{"texto": c["texto"], "esperado": c["esperado_docs"], "tipo": c["origen"]}
          for c in casos if c["grupo"] == "rag"]
    clasificadores = _clasificadores(config)
    print(f"  guardrail ({len(gr)} frases)")
    for nombre, clf in clasificadores.items():
        r = medir(gr, clf)
        print("   ", _linea(nombre, r))
        if fallos:
            for c, pred in r["fallos"]:
                print(f"       esperado={c['esperado']} obtenido={pred} :: {c['texto'][:90]}")
    if pe:
        print(f"  pedidos ({len(pe)} frases)")
        for nombre, clf in clasificadores.items():
            if clf is None:
                continue
            r = medir_pedidos(pe, clf)
            print("   ", _linea_pedidos(nombre, r))
            if fallos:
                for c, motivo in r["fallos"]:
                    print(f"       {motivo} :: {c['texto'][:90]}")
    if ra:
        indice = cargar_indice()
        buscadores = {"BM25 solo": indice.buscar}
        if config.embedding_model and config.proveedor == "openai":
            buscadores[f"híbrido ({config.embedding_model})"] = RecuperadorHibrido(indice, ClienteEmbeddings(config)).buscar
        print(f"  recuperación de documentos ({len(ra)} preguntas)")
        for nombre, buscar in buscadores.items():
            r = medir_rag(ra, buscar)
            print("   ", _linea_rag(nombre, r))
            if fallos:
                for c, obtenidos in r["fallos"]:
                    print(f"       esperado={c['esperado']} obtenido={obtenidos} :: {c['texto'][:90]}")


def main(argv: list[str]) -> int:
    orden = argv[0] if argv else "medir"
    if orden == "importar":
        casos = importar(open(argv[1], encoding="utf-8").read())
        print(f"{len(casos)} frases importadas en {ARCHIVO}")
        return 0
    if orden == "variantes":
        manuales = open(argv[1], encoding="utf-8").read() if len(argv) > 1 else ""
        print(f"{len(agregar_variantes(manuales=manuales))} variantes agregadas")
        return 0
    casos = cargar()
    if not casos:
        print(f"No hay frases en {ARCHIVO}. Usar `importar` primero.")
        return 1
    config = Config()
    for origen in ("Ramiro", "variante"):
        subset = [c for c in casos if c["origen"] == origen]
        if subset:
            print(f"\n== {'frases originales de Ramiro' if origen == 'Ramiro' else 'variantes derivadas'} ({len(subset)}) ==")
            medir_origen(subset, config, "--fallos" in argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
