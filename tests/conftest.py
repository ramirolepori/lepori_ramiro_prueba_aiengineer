"""Los tests no usan red ni el .env local: se fuerza el modo offline antes de importar el paquete."""

import os

os.environ["LLM_PROVIDER"] = "none"
os.environ["EMBEDDING_MODEL"] = ""
os.environ["EMBEDDINGS_CACHE"] = "none"


import pytest


@pytest.fixture(autouse=True)
def _servicios_sin_caidas():
    """Cada test arranca sin servicios marcados como caídos."""
    from tiendahogar import llm
    llm._CAIDOS.clear()
    yield
    llm._CAIDOS.clear()
