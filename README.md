# Agente de soporte de TiendaHogar

Agente de soporte que responde preguntas sobre garantías, devoluciones, envíos y reembolsos con RAG sobre los 5 documentos del enunciado, consulta el estado de un pedido con la tool `consultar_estado_pedido` y deriva a una persona los casos que no debe resolver (reembolsos mayores a $500, quejas de trato, disputas de facturación, temas legales). Responde en español.

El flujo lo decide el código y el LLM solo redacta con lo recuperado, así que el comportamiento crítico no depende del modelo. Las decisiones y sus trade-offs están en `SUBMISSION.md`.

## Qué hace el agente con cada pregunta

1. Si intenta cambiar las reglas del agente (inyección de prompt evidente), la rechaza.
2. Si es un reembolso mayor a $500, una queja de trato, una disputa de facturación o un tema legal, deriva a soporte@tiendahogar.example. Lo detecta con reglas y, además, por significado (paráfrasis y faltas de ortografía). Hasta $500 no deriva: informa la política (plazo y método de pago) y aclara que no hace falta un supervisor. No confirma ni promete que un reembolso esté aprobado o ejecutado, porque el agente no tiene una herramienta para hacerlo.
3. Si la pregunta mezcla algo para derivar con algo permitido, responde primero lo permitido y después deriva.
4. Si menciona un número de pedido, consulta la tool. Entiende `ORD-1001`, `ord1001`, `pedido 1001`, `orden de compra 1001`, "mi pedido es el 1001" y listas, y muestra qué número entendió. También "compra nro 1003" y "n°2000". Un número inexistente devuelve "No encontrado" sin inventar datos, y un identificador con otro formato (`DRO-1002`, `ORD1OO1`) no se corrige en silencio: el agente dice que no lo encontró y cuál es el formato. Si pregunta por un pedido sin dar el número ("ya salió lo que compré?"), lo pide: no busca por nombre de producto.
5. Busca en los documentos por significado y por palabras (embeddings más BM25, fusionados), para la consulta entera y para cada cláusula. Si ninguno es relevante, responde que no tiene esa información.
   Para los envíos, el plazo lo decide el código según el lugar (`lugares.py`): "la capital" es la Ciudad de Buenos Aires (CABA), "Córdoba capital" cuenta como otra ciudad, "Buenos Aires" a secas es ambiguo y un país del exterior no tiene envío. Si no hay lugar, informa los dos plazos y pide la ciudad.
6. Redacta la respuesta citando el documento, con el LLM si hay uno configurado o citando el texto del documento si no. Con LLM, el código revisa después que la respuesta cubra los dos documentos más relevantes (si la pregunta mezcla garantía y devolución, por ejemplo, completa el que falte) y agrega las aclaraciones obligatorias, como la regla de los $500, sin depender de que el modelo las copie.

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

`pytest tests/` alcanza si `pytest` ya está instalado. No hace falta instalar el paquete: `pyproject.toml` ya agrega `src` al path de pytest. Los tests no usan red ni el `.env`: corren con el modo offline.

Hay un test opt-in que mide el guardrail con embeddings reales y necesita Ollama con `embeddinggemma`: `TIENDAHOGAR_TEST_OLLAMA=1 pytest tests/test_semantica.py`.

## Correr el agente

Desde la raíz del repo, con `PYTHONPATH=src` (PowerShell: `$env:PYTHONPATH = "src"`; bash: `export PYTHONPATH=src`):

```
python -m tiendahogar "Cuánto dura la garantía de una licuadora?"
python -m tiendahogar            # chat interactivo con memoria de sesión, línea vacía para salir
```

Con una sola pregunta el agente no recuerda nada. En el chat interactivo (o desde código con `agente.responder(pregunta, Sesion())`) recuerda qué dato le pidió al cliente: si falta el lugar, el monto de un reembolso o el número de pedido, lo repregunta (como máximo 2 veces, y se olvida a los 5 mensajes) y usa la respuesta. Sin sesión, cada pregunta es independiente.

En Windows, si la consola muestra mal las tildes: `$env:PYTHONUTF8 = "1"`.

Desde código:

```python
from tiendahogar import AgenteSoporte, consultar_estado_pedido

consultar_estado_pedido("ORD-1001")
# {'order_id': 'ORD-1001', 'encontrado': True, 'producto': 'Refrigeradora', 'estado': 'En tránsito', 'entrega_estimada': '3 días hábiles'}
consultar_estado_pedido("ORD-9999")
# {'order_id': 'ORD-9999', 'encontrado': False, 'estado': 'No encontrado', 'mensaje': 'No existe un pedido con ese número en el sistema.'}

r = AgenteSoporte().responder("Quiero un reembolso de $900")
r.estado       # 'escalado'
r.texto        # deriva a soporte@tiendahogar.example
r.escalamientos, r.fuentes, r.pedidos, r.traza     # categorías, documentos citados, pedidos, pasos del agente
```

`r.estado` puede ser `respondido`, `escalado`, `sin_informacion` o `bloqueado`.

## Variables de entorno

Copiar `.env.example` a `.env` (ignorado por git) o definirlas en el entorno. Ninguna es obligatoria.

| Variable | Qué hace |
| --- | --- |
| `LLM_PROVIDER` | `none` (por defecto, modo offline), `openai` (cualquier API compatible con OpenAI) o `anthropic` |
| `LLM_MODEL` | Modelo que redacta las respuestas |
| `EMBEDDING_MODEL` | Modelo de embeddings del guardrail (solo con `openai`). Sin él se usan reglas y n-gramas de caracteres |
| `LLM_API_KEY` | Clave. Puede quedar vacía con un servidor local como Ollama |
| `LLM_BASE_URL` | Solo con `openai`. Por defecto `https://api.openai.com/v1`. Ollama: `http://localhost:11434/v1` |
| `LLM_TIMEOUT_S`, `LLM_MAX_TOKENS` | Tiempo máximo por llamada (60 s) y tokens de salida (1024) |

`LLM_PROVIDER=openai` sirve para cualquier API compatible con OpenAI y solo cambia `LLM_BASE_URL`, `LLM_MODEL` y `LLM_API_KEY`. Con los modelos de razonamiento de OpenAI, que rechazan `max_tokens` y `temperature`, el cliente reintenta solo con `max_completion_tokens`.

Ejemplo con OpenAI (PowerShell):

```powershell
$env:LLM_PROVIDER = "openai"; $env:LLM_MODEL = "<modelo>"; $env:LLM_API_KEY = "<clave>"; $env:EMBEDDING_MODEL = "text-embedding-3-small"
```

Ejemplo con modelos locales en Ollama (`ollama pull qwen2.5:7b` y `ollama pull embeddinggemma`):

```powershell
$env:LLM_PROVIDER = "openai"; $env:LLM_BASE_URL = "http://127.0.0.1:11434/v1"; $env:LLM_MODEL = "qwen2.5:7b"; $env:EMBEDDING_MODEL = "embeddinggemma"
```

Conviene escribir `127.0.0.1` y no `localhost`: en Windows `localhost` prueba primero IPv6 y cada llamada pierde unos 2 segundos (con `127.0.0.1` son unos 45 ms). El cliente ya reemplaza `localhost` por `127.0.0.1` solo, pero la aclaración evita sorpresas con otros clientes.

`EMBEDDINGS_CACHE` es la carpeta donde se guardan los embeddings de los textos fijos (documentos y frases de ejemplo del guardrail) para que el arranque no los pida de nuevo; por defecto `.cache/` y `none` la desactiva. Nunca se guardan preguntas de clientes.

Si el proveedor falla (red, clave, tiempo), el agente lo registra en la traza y sigue en modo offline: el guardrail pasa a n-gramas, la recuperación a BM25 y la respuesta cita el documento. Una conexión rechazada falla enseguida y un servicio que falló no se vuelve a intentar durante 30 segundos, así que un servidor caído no ralentiza cada pregunta. Una configuración inválida (`LLM_PROVIDER` desconocido, falta de modelo o de clave) termina con un mensaje claro y código de salida 2. Las consultas de más de 2000 caracteres se recortan.

## Medir el agente

```
python -m tiendahogar.evaluacion              # guardrail: reglas, reglas + n-gramas y reglas + embeddings (si hay)
python -m tiendahogar.evaluacion pedidos      # extracción de números de pedido e intención de consulta
python -m tiendahogar.evaluacion rag          # recuperación de documentos: BM25 contra híbrido
python -m tiendahogar.independiente medir     # frases escritas por otra persona (conjunto independiente), por origen
python -m tiendahogar.evaluacion --fallos     # además, lista los casos que fallan (se puede sumar a cualquiera)
python -m tiendahogar.evaluacion --barrido    # además, barre el margen del guardrail sobre el conjunto de desarrollo
```

Cada medición usa un conjunto de `tests/data/` dividido en desarrollo (para ajustar márgenes) y prueba (sin tocar al ajustar). Sin `EMBEDDING_MODEL` solo se miden las variantes sin red. Los resultados y sus salvedades están en `SUBMISSION.md`.

## Medir el rendimiento

```
python -m tiendahogar.rendimiento              # con lo configurado en .env (modelo de lenguaje y embeddings)
python -m tiendahogar.rendimiento --sin-llm    # sin modelo de lenguaje: mide la herramienta con embeddings
python -m tiendahogar.rendimiento --offline    # sin ningún modelo: reglas, n-gramas y BM25
```

Separa el tiempo de cada respuesta en tres baldes: el modelo de lenguaje, el modelo de embeddings (los dos dependen del modelo y del hardware) y el código propio, que es lo que se puede optimizar desde acá. Cada respuesta del agente trae esos números en `Respuesta.tiempos` y en la traza. Los resultados están en `SUBMISSION.md`.

## Estructura

```
src/tiendahogar/
  agent.py        flujo de decisión del agente, preguntas mixtas y validación de la salida del LLM
  guardrails.py   escalamiento a humano (reglas) y detección de inyección
  semantica.py    clasificación por significado: embeddings y n-gramas, evaluación por oración
  montos.py       extracción de montos en distintos formatos ($1.000, 2k, mil quinientos, USD600)
  rag.py          chunking, BM25 y recuperador híbrido (embeddings más BM25)
  embeddings.py   cliente de embeddings (/v1/embeddings) y similitud coseno
  pedidos.py      tool consultar_estado_pedido, tabla mock y extracción flexible de números de pedido
  lugares.py      plazo de envío según el lugar: gazetteer (data/lugares.json) y reglas; "la capital" es la Ciudad de Buenos Aires
  sesion.py       memoria de la conversación: qué dato pidió el agente (lugar, monto, número de pedido) y cómo se lee la respuesta
  llm.py          clientes OpenAI-compatible y Anthropic (urllib, sin dependencias)
  evaluacion.py   medición del guardrail, de los pedidos y del RAG
  independiente.py  conjunto de frases escritas por otra persona: importar, variantes y medir
  rendimiento.py  latencia por etapa (modelo de lenguaje, embeddings, código propio)
  tiempos.py      cronómetro por etapa
  config.py       variables de entorno
  data/docs/      los 5 documentos del enunciado, sin editar
  data/anclas.json  frases de ejemplo por categoría del guardrail y de la consulta de pedidos
  data/fuera_de_alcance.json  preguntas que los documentos no responden (referencia del umbral del RAG)
tests/            pytest: RAG, tool, guardrails, montos, capa semántica, preguntas mixtas y escenarios de punta a punta
```

Las trazas de `python -m tiendahogar` se guardan en `trazas/trazas.jsonl` (ignorada por git).

## Limitaciones

Están detalladas en `SUBMISSION.md`. Las principales: el agente solo trabaja en español, no recuerda mensajes anteriores, los clientes de LLM no se probaron contra la API de un proveedor comercial y las cifras de medición del guardrail salen de un conjunto escrito por el mismo autor del código.
