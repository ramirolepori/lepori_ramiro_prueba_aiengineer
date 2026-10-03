"""Chat de consola:  python -m tiendahogar             (interactivo)
                    python -m tiendahogar "pregunta"  (una sola pregunta)"""

import sys

from .agent import AgenteSoporte
from .config import RAIZ
from .llm import ErrorLLM, crear_llm
from .sesion import Sesion


def main() -> int:
    try:
        agente = AgenteSoporte(llm=crear_llm(), trazas_dir=RAIZ / "trazas")
    except ErrorLLM as e:
        print(f"Configuración de LLM inválida: {e}", file=sys.stderr)
        return 2
    modo = "con LLM" if agente.llm else "offline (sin LLM)"
    if len(sys.argv) > 1:
        print(agente.responder(" ".join(sys.argv[1:])).texto)
        return 0
    print(f"Soporte TiendaHogar [{modo}]. Línea vacía para salir.")
    sesion = Sesion()          # en el chat interactivo el agente recuerda lo que le preguntó al cliente
    while True:
        try:
            pregunta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pregunta:
            break
        print(agente.responder(pregunta).texto, "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
