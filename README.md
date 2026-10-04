# Agente de soporte de TiendaHogar

Agente de soporte que responde preguntas sobre garantías, devoluciones, envíos y reembolsos con RAG sobre los 5 documentos del enunciado, consulta el estado de un pedido con la tool `consultar_estado_pedido` y deriva a una persona (soporte@tiendahogar.example) lo que no debe resolver: reembolsos mayores a $500, quejas por el trato de un empleado, disputas de facturación, temas legales e incidentes de seguridad con un producto (una lesión, un cortocircuito). Responde en español.

El flujo lo decide el código y el modelo de lenguaje solo redacta con lo recuperado, así que el comportamiento crítico no depende del modelo. Sin modelo configurado el agente funciona completo en modo offline.

Más detalle: [SUBMISSION.md](SUBMISSION.md) (la entrega), [docs/arquitectura.md](docs/arquitectura.md) (flujo, módulos y cómo extenderlo) y [docs/adr](docs/adr/README.md) (cada decisión con sus alternativas y su evidencia).

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

Lo primero que hay que leer es [tests/test_criticos.py](tests/test_criticos.py): los comportamientos que pide el enunciado (RAG con cita, tool de pedidos y derivación a una persona), en pocos tests y sin modelo. El resto cubre variantes, ataques y la memoria de la conversación.

Con `pytest` ya instalado alcanza con `pytest tests/`. Los tests no usan red ni el `.env` (corren en modo offline, unos 20 segundos). Hay dos tests opt-in que necesitan Ollama con `embeddinggemma`: `TIENDAHOGAR_TEST_OLLAMA=1 pytest tests/test_semantica.py`.

## Correr el agente

Desde la raíz del repositorio, con `PYTHONPATH=src` (PowerShell: `$env:PYTHONPATH = "src"`; bash: `export PYTHONPATH=src`):

```
python -m tiendahogar "Cuánto dura la garantía de una licuadora?"
python -m tiendahogar            # chat interactivo, línea vacía para salir
```

En Windows, si la consola muestra mal las tildes: `$env:PYTHONUTF8 = "1"`.

Con una sola pregunta el agente no recuerda nada. En el chat interactivo (o desde código con `agente.responder(pregunta, Sesion())`) recuerda qué dato le pidió al cliente (el lugar de un envío, el monto de un reembolso, el número de un pedido o hace cuánto compró) y lo que ya dijo (pedido, lugar y monto), lo repregunta como máximo 2 veces y se olvida a los 5 mensajes. Sin sesión, cada pregunta es independiente (en el chat se logra con `python -m tiendahogar --sin-memoria`).

Desde código:

```python
from tiendahogar import AgenteSoporte, consultar_estado_pedido

consultar_estado_pedido("ORD-1001")   # {'order_id': 'ORD-1001', 'encontrado': True, 'producto': 'Refrigeradora', ...}
r = AgenteSoporte().responder("Quiero un reembolso de $900")
r.estado    # 'escalado' (también 'respondido', 'sin_informacion' o 'bloqueado')
r.texto     # el mensaje para el cliente; además r.fuentes, r.escalamientos, r.pedidos y r.traza
```

## Qué hace con cada pregunta

1. Rechaza un intento evidente de cambiar sus reglas (inyección de prompt).
2. Deriva los casos que no debe resolver, por reglas y por significado (paráfrasis, jerga, faltas de ortografía). Hasta $500 informa la política sin prometer nada; si falta el monto, lo pregunta. Si la pregunta mezcla algo para derivar con algo permitido, responde primero lo permitido.
3. Si menciona un número de pedido (`ORD-1001`, `pedido 1001`, `compra nro 1003`...), consulta la tool y muestra qué número entendió. Un número inexistente o con otro formato devuelve "No encontrado" sin inventar ni corregir en silencio.
4. Busca en los documentos (embeddings más BM25). Si ninguno es relevante, responde que no tiene esa información y no llama al modelo. El plazo de envío lo decide el código según el lugar ("la capital" es la Ciudad de Buenos Aires).
5. Redacta citando el documento, con el modelo si hay uno o con el texto del documento si no. El código valida la respuesta y agrega las aclaraciones obligatorias.

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

Si el proveedor falla, el agente lo anota en la traza y sigue en modo offline. Una configuración inválida termina con un mensaje claro y código de salida 2.

## Medir el agente

```
python -m tiendahogar.evaluacion [pedidos|rag] [--fallos]   # guardrail, pedidos y recuperación de documentos
python -m tiendahogar.independiente medir                    # lotes de frases escritas por otra persona
python -m tiendahogar.rendimiento [--sin-llm|--offline]      # latencia por etapa
```

Los conjuntos de frases están en `tests/data/`, divididos en desarrollo y prueba. Los resultados y sus salvedades están en los ADR [0003](docs/adr/0003-guardrail-en-tres-capas.md), [0004](docs/adr/0004-rag-hibrido-y-umbral-por-margen.md), [0009](docs/adr/0009-modelos-locales-y-clientes-sin-sdk.md), [0010](docs/adr/0010-estrategia-de-evaluacion.md) y [0011](docs/adr/0011-robustez-ante-intentos-de-sacarlo-de-alcance.md).

## Estructura

```
src/tiendahogar/   código del agente (solo librería estándar); data/ trae los 5 documentos sin editar
tests/             pytest: RAG, tool, guardrails, lugares, sesión, ataques y escenarios de punta a punta
docs/              arquitectura.md y adr/ (registro de decisiones)
SUBMISSION.md      la entrega con la plantilla del enunciado
```

Las trazas de `python -m tiendahogar` van a `trazas/trazas.jsonl` (ignorada por git) y no incluyen el texto de las consultas.

## Limitaciones

Están en [SUBMISSION.md](SUBMISSION.md). Las principales: trabaja en español, los clientes de modelo no se probaron contra la API de un proveedor comercial, la memoria se limita a cuatro datos y las cifras de medición salen de conjuntos de frases escritos por el mismo autor del código o ajustados mirándolos.
