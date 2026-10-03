"""Chat de consola:  python -m tiendahogar             (interactivo)
                    python -m tiendahogar --sin-memoria  (interactivo, cada pregunta independiente)
                    python -m tiendahogar "pregunta"  (una sola pregunta)"""

import re
import sys

from .agent import AgenteSoporte
from .config import RAIZ
from .llm import ErrorLLM, crear_llm
from .sesion import Sesion

_FUENTES = {"devoluciones": "política de devoluciones", "garantia": "política de garantía", "envios": "política de envíos",
            "reembolsos": "política de reembolsos", "contacto": "información de contacto"}


def para_mostrar(texto: str) -> str:
    """En la consola las citas [doc] del texto se muestran como una línea final de fuentes, más natural de leer."""
    docs = list(dict.fromkeys(re.findall(r"\[(\w+)\]", texto)))
    limpio = re.sub(r" ?\[\w+\]", "", texto).strip()
    if not docs:
        return limpio
    return f"{limpio}\n(Fuente: {', '.join(_FUENTES.get(d, d) for d in docs)})"


def main() -> int:
    try:
        agente = AgenteSoporte(llm=crear_llm(), trazas_dir=RAIZ / "trazas")
    except ErrorLLM as e:
        print(f"Configuración de LLM inválida: {e}", file=sys.stderr)
        return 2
    modo = "con LLM" if agente.llm else "offline (sin LLM)"
    args = [a for a in sys.argv[1:] if a != "--sin-memoria"]
    sin_memoria = len(args) != len(sys.argv) - 1
    if args:
        print(para_mostrar(agente.responder(" ".join(args)).texto))
        return 0
    print(f"Soporte TiendaHogar [{modo}{', sin memoria' if sin_memoria else ''}]. Línea vacía para salir.")
    # en el chat interactivo el agente recuerda lo que le preguntó al cliente (salvo con --sin-memoria)
    sesion = None if sin_memoria else Sesion()
    while True:
        try:
            pregunta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pregunta:
            break
        print(para_mostrar(agente.responder(pregunta, sesion).texto), "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
