"""Configuración por variables de entorno (o un .env en la raíz del repo). Nunca hay claves en el código."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _cargar_dotenv(ruta: Path) -> None:
    """Lee un .env simple (CLAVE=valor) sin pisar variables ya definidas."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_dotenv(RAIZ / ".env")


def _entorno(nombre: str, defecto: str) -> str:
    """Variable de entorno; una variable vacía (como en .env.example) cuenta como no definida."""
    return os.getenv(nombre) or defecto


@dataclass
class Config:
    proveedor: str = field(default_factory=lambda: _entorno("LLM_PROVIDER", "none").lower())
    modelo: str = field(default_factory=lambda: _entorno("LLM_MODEL", ""))
    api_key: str = field(default_factory=lambda: _entorno("LLM_API_KEY", ""))
    base_url: str = field(default_factory=lambda: _entorno("LLM_BASE_URL", "https://api.openai.com/v1"))
    timeout_s: float = field(default_factory=lambda: float(_entorno("LLM_TIMEOUT_S", "60")))
    max_tokens: int = field(default_factory=lambda: int(_entorno("LLM_MAX_TOKENS", "1024")))
