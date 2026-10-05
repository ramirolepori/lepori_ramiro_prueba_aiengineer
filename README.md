# Agente de soporte de TiendaHogar

Agente de soporte con RAG sobre los 5 documentos del enunciado y la tool `consultar_estado_pedido`. Responde sobre garantías, devoluciones, envíos y reembolsos, y deriva a una persona (soporte@tiendahogar.example) lo que no debe resolver: reembolsos mayores a $500, quejas por el trato de un empleado, disputas de facturación, temas legales e incidentes de seguridad. Responde en español. El código decide el flujo y el modelo solo redacta, así que sin modelo configurado funciona completo en modo offline.

La entrega (arquitectura y decisiones) está en [SUBMISSION.md](SUBMISSION.md), los módulos y cómo extenderlo en [docs/arquitectura.md](docs/arquitectura.md), y cada decisión en [docs/adr](docs/adr/README.md).

## Instalación y tests

Python 3.10 o superior. El agente usa solo la librería estándar; los tests necesitan `pytest`.

```powershell
# PowerShell (Windows)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests/
```

```bash
# macOS y Linux
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/
```

Con `pytest` ya instalado alcanza con `pytest tests/`. Corren en unos 25 segundos, sin red ni `.env`. Lo primero que hay que leer es [tests/test_criticos.py](tests/test_criticos.py). Dos tests opt-in necesitan Ollama con `embeddinggemma`: `TIENDAHOGAR_TEST_OLLAMA=1 pytest tests/test_semantica.py`.

## Correr el agente

Desde la raíz del repositorio, con `PYTHONPATH=src` (PowerShell: `$env:PYTHONPATH = "src"`; bash: `export PYTHONPATH=src`). En Windows, si la consola muestra mal las tildes: `$env:PYTHONUTF8 = "1"`.

```
python -m tiendahogar "Cuánto dura la garantía de una licuadora?"
python -m tiendahogar            # chat con memoria; línea vacía para salir (--sin-memoria la desactiva)
```

Desde código:

```python
from tiendahogar import AgenteSoporte, consultar_estado_pedido

consultar_estado_pedido("ORD-1001")   # {'order_id': 'ORD-1001', 'encontrado': True, 'producto': 'Refrigeradora', ...}
r = AgenteSoporte().responder("Quiero un reembolso de $900")
r.estado    # 'escalado' (o 'respondido', 'sin_informacion', 'bloqueado'); además r.texto, r.fuentes, r.pedidos y r.traza
```

Sin sesión cada pregunta es independiente. Con `responder(pregunta, Sesion())` el agente recuerda el dato que le pidió al cliente (lugar, monto, pedido o hace cuánto compró) y lo repregunta como máximo 2 veces.

## Variables de entorno

Copiar `.env.example` a `.env` (ignorado por git) o definirlas en el entorno. Ninguna es obligatoria.

| Variable | Qué hace |
| --- | --- |
| `LLM_PROVIDER` | `none` (por defecto, modo offline), `openai` (cualquier API compatible con OpenAI) o `anthropic` |
| `LLM_MODEL`, `LLM_API_KEY` | Modelo que redacta y su clave (puede quedar vacía con un servidor local como Ollama) |
| `LLM_BASE_URL` | Solo con `openai`. Por defecto `https://api.openai.com/v1`; Ollama: `http://127.0.0.1:11434/v1` |
| `EMBEDDING_MODEL` | Modelo de embeddings del guardrail y del recuperador (solo con `openai`). Sin él se usan reglas, n-gramas y BM25 |
| `LLM_TIMEOUT_S`, `LLM_MAX_TOKENS` | Tiempo máximo por llamada (60 s) y tokens de salida (1024) |
| `EMBEDDINGS_CACHE` | Carpeta de la caché de embeddings de textos fijos (por defecto `.cache/`; `none` la desactiva) |

```powershell
# OpenAI
$env:LLM_PROVIDER = "openai"; $env:LLM_MODEL = "<modelo>"; $env:LLM_API_KEY = "<clave>"; $env:EMBEDDING_MODEL = "text-embedding-3-small"
# Modelos locales en Ollama (ollama pull qwen2.5:7b y ollama pull embeddinggemma)
$env:LLM_PROVIDER = "openai"; $env:LLM_BASE_URL = "http://127.0.0.1:11434/v1"; $env:LLM_MODEL = "qwen2.5:7b"; $env:EMBEDDING_MODEL = "embeddinggemma"
```

Si el proveedor falla, el agente sigue en modo offline. Una configuración inválida termina con un mensaje claro y código de salida 2.

## Medir el agente

```
python -m tiendahogar.evaluacion [pedidos|rag] [--fallos]   # guardrail, pedidos y recuperación de documentos
python -m tiendahogar.independiente medir                    # lotes de frases escritas por otra persona
python -m tiendahogar.rendimiento [--sin-llm|--offline]      # latencia por etapa
```

Los resultados y sus salvedades están en los ADR [0002](docs/adr/0002-guardrail-y-robustez.md), [0003](docs/adr/0003-recuperacion-y-pedidos.md) y [0006](docs/adr/0006-modelos-y-evaluacion.md). El CLI guarda su traza en `trazas/trazas.jsonl` (ignorada por git, sin el texto de las consultas). Las limitaciones están en [SUBMISSION.md](SUBMISSION.md).
