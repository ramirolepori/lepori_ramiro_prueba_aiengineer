# Agente de soporte de TiendaHogar

Agente de soporte que responde preguntas sobre garantías, devoluciones, envíos y reembolsos con RAG sobre los 5 documentos del enunciado, consulta el estado de un pedido con la tool `consultar_estado_pedido` y deriva a una persona los casos que no debe resolver (reembolsos mayores a $500, quejas de trato, disputas de facturación, temas legales).

Corre sin clave y sin dependencias: sin LLM configurado responde citando los documentos tal cual. Con un LLM, el modelo solo redacta la respuesta a partir de lo recuperado. El diseño y sus decisiones están en `SUBMISSION.md`.

## Requisitos

Python 3.10 o superior. El código del agente usa solo la librería estándar. Para los tests hace falta `pytest`.

## Instalación y tests

PowerShell (Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests/
```

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/
```

`pytest tests/` alcanza si `pytest` ya está instalado. No hace falta instalar el paquete: `pyproject.toml` ya agrega `src` al path de pytest.

## Correr el agente

Desde la raíz del repo, con `PYTHONPATH=src` (PowerShell: `$env:PYTHONPATH = "src"`; bash: `export PYTHONPATH=src`):

```
python -m tiendahogar "Cuánto dura la garantía de una licuadora?"
python -m tiendahogar            # chat interactivo, línea vacía para salir
```

En Windows, si la consola muestra mal las tildes: `$env:PYTHONUTF8 = "1"`.

Desde código:

```python
from tiendahogar import AgenteSoporte, consultar_estado_pedido

consultar_estado_pedido("ORD-1001")
# {'order_id': 'ORD-1001', 'encontrado': True, 'producto': 'Refrigeradora', 'estado': 'En tránsito', 'entrega_estimada': '3 días hábiles'}
consultar_estado_pedido("ORD-9999")
# {'order_id': 'ORD-9999', 'encontrado': False, 'estado': 'No encontrado', 'mensaje': 'No existe un pedido con ese número en el sistema.'}

r = AgenteSoporte().responder("Quiero un reembolso de $900")
r.estado      # 'escalado'
r.texto       # deriva a soporte@tiendahogar.example
```

## Variables de entorno

Copiar `.env.example` a `.env` (ignorado por git) o definirlas en el entorno. Ninguna es obligatoria.

| Variable | Qué hace |
| --- | --- |
| `LLM_PROVIDER` | `none` (por defecto, modo offline), `openai` (cualquier API compatible con OpenAI) o `anthropic` |
| `LLM_MODEL` | Nombre del modelo |
| `LLM_API_KEY` | Clave. Puede quedar vacía con un servidor local como Ollama |
| `LLM_BASE_URL` | Solo con `openai`. Por defecto `https://api.openai.com/v1`. Ollama: `http://localhost:11434/v1` |
| `LLM_TIMEOUT_S`, `LLM_MAX_TOKENS` | Tiempo máximo por llamada (60 s) y tokens de salida (500) |

Ejemplo con un modelo local en Ollama (PowerShell):

```powershell
$env:LLM_PROVIDER = "openai"; $env:LLM_BASE_URL = "http://localhost:11434/v1"; $env:LLM_MODEL = "qwen2.5:3b"
```

Si el proveedor falla (red, clave, tiempo), el agente lo registra en la traza y responde en modo offline.

## Estructura

```
src/tiendahogar/
  agent.py        flujo de decisión del agente
  guardrails.py   escalamiento a humano y detección de inyección (reglas determinísticas)
  rag.py          chunking, BM25 con umbral
  pedidos.py      tool consultar_estado_pedido y tabla mock
  llm.py          clientes OpenAI-compatible y Anthropic (urllib, sin dependencias)
  config.py       variables de entorno
  data/docs/      los 5 documentos del enunciado, sin editar
tests/            pytest: RAG, tool, guardrails y escenarios de punta a punta
```

Las trazas de `python -m tiendahogar` se guardan en `trazas/trazas.jsonl` (ignorada por git).
