"""Los tests no usan red ni el .env local: se fuerza el modo offline antes de importar el paquete."""

import os

os.environ["LLM_PROVIDER"] = "none"
os.environ["EMBEDDING_MODEL"] = ""
os.environ["EMBEDDINGS_CACHE"] = "none"
