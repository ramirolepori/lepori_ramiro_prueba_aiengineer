# Agente de soporte de TiendaHogar

Agente de soporte que responde preguntas sobre garantías, devoluciones, envíos y reembolsos con RAG sobre los 5 documentos del enunciado, consulta el estado de un pedido con la tool `consultar_estado_pedido` y deriva a una persona los casos que no debe resolver (reembolsos mayores a $500, quejas de trato, disputas de facturación y temas legales). Responde en español.

El flujo lo decide el código y el modelo de lenguaje solo redacta con lo recuperado, así que el comportamiento crítico no depende del modelo. Sin modelo configurado el agente funciona completo en modo offline.

Documentación: [SUBMISSION.md](SUBMISSION.md) (la entrega, con la plantilla del enunciado), [docs/arquitectura.md](docs/arquitectura.md) (flujo, módulos y cómo extenderlo) y [docs/adr](docs/adr/README.md) (cada decisión de diseño con sus alternativas y su evidencia).

## Requisitos

Python 3.10 o superior. El código del agente usa solo la librería estándar. Para los tests hace falta `pytest`.

## Instalación y tests

PowerShell (Windows):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests/
```

macOS y Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest tests/
```

Con `pytest` ya instalado alcanza con `pytest tests/`. No hace falta instalar el paquete: `pyproject.toml` ya agrega `src` al path de pytest. Los tests no usan red ni el `.env`: corren en modo offline y tardan unos 20 segundos.

Hay dos tests opt-in que miden el guardrail con embeddings reales y necesitan Ollama con `embeddinggemma`: `TIENDAHOGAR_TEST_OLLAMA=1 pytest tests/test_semantica.py`.

## Correr el agente

Desde la raíz del repositorio, con `PYTHONPATH=src` (PowerShell: `$env:PYTHONPATH = "src"`; bash: `export PYTHONPATH=src`):

```
python -m tiendahogar "Cuánto dura la garantía de una licuadora?"
python -m tiendahogar            # chat interactivo con memoria de sesión, línea vacía para salir
```

En Windows, si la consola muestra mal las tildes: `$env:PYTHONUTF8 = "1"`.

Con una sola pregunta el agente no recuerda nada. En el chat interactivo (o desde código con `agente.responder(pregunta, Sesion())`) recuerda qué dato le pidió al cliente: si falta el lugar para un envío, el monto de un reembolso o el número de un pedido, lo repregunta (como máximo 2 veces, y se olvida a los 5 mensajes) y usa la respuesta. Sin sesión, cada pregunta es independiente.

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

## Qué hace el agente con cada pregunta

1. Rechaza un intento evidente de cambiar sus reglas (inyección de prompt).
2. Deriva a soporte@tiendahogar.example los reembolsos mayores a $500, las quejas por el trato de un empleado, las disputas de facturación y los temas legales. Lo detecta con reglas y, además, por significado (paráfrasis, jerga y faltas de ortografía). Hasta $500 no deriva: informa la política y aclara que no hace falta un supervisor, sin prometer que el reembolso esté aprobado. Si falta el monto, lo pregunta.
3. Si la pregunta mezcla algo para derivar con algo permitido, responde primero lo permitido y después deriva.
4. Si menciona un número de pedido (`ORD-1001`, `pedido 1001`, `compra nro 1003`...), consulta la tool y muestra qué número entendió. Un número inexistente o un identificador con otro formato devuelve "No encontrado" sin inventar datos ni corregir en silencio. Si pregunta por un pedido sin dar el número, lo pide.
5. Busca en los documentos por significado y por palabras (embeddings más BM25). Si ninguno es relevante, responde que no tiene esa información. Para los envíos, el plazo lo decide el código según el lugar: "la capital" es la Ciudad de Buenos Aires, "Córdoba capital" cuenta como otra ciudad, "Buenos Aires" a secas se repregunta y un país del exterior no tiene envío.
6. Redacta citando el documento, con el modelo si hay uno configurado o con el texto del documento si no. Después el código valida la respuesta, completa la cobertura de las políticas y agrega las aclaraciones obligatorias.

## Variables de entorno

Copiar `.env.example` a `.env` (ignorado por git) o definirlas en el entorno. Ninguna es obligatoria.

| Variable | Qué hace |
| --- | --- |
| `LLM_PROVIDER` | `none` (por defecto, modo offline), `openai` (cualquier API compatible con OpenAI) o `anthropic` |
| `LLM_MODEL` | Modelo que redacta las respuestas |
| `EMBEDDING_MODEL` | Modelo de embeddings del guardrail y del recuperador (solo con `openai`). Sin él se usan reglas, n-gramas de caracteres y BM25 |
| `LLM_API_KEY` | Clave. Puede quedar vacía con un servidor local como Ollama |
| `LLM_BASE_URL` | Solo con `openai`. Por defecto `https://api.openai.com/v1`. Ollama: `http://127.0.0.1:11434/v1` |
| `LLM_TIMEOUT_S`, `LLM_MAX_TOKENS` | Tiempo máximo por llamada (60 s) y tokens de salida (1024) |
| `EMBEDDINGS_CACHE` | Carpeta de la caché de embeddings de textos fijos (por defecto `.cache/`; `none` la desactiva). Nunca guarda preguntas de clientes |

`LLM_PROVIDER=openai` sirve para cualquier API compatible con OpenAI y solo cambia `LLM_BASE_URL`, `LLM_MODEL` y `LLM_API_KEY`. Con los modelos de razonamiento de OpenAI, que rechazan `max_tokens` y `temperature`, el cliente reintenta con `max_completion_tokens`.

Ejemplo con OpenAI (PowerShell):

```powershell
$env:LLM_PROVIDER = "openai"; $env:LLM_MODEL = "<modelo>"; $env:LLM_API_KEY = "<clave>"; $env:EMBEDDING_MODEL = "text-embedding-3-small"
```

Ejemplo con modelos locales en Ollama (`ollama pull qwen2.5:7b` y `ollama pull embeddinggemma`):

```powershell
$env:LLM_PROVIDER = "openai"; $env:LLM_BASE_URL = "http://127.0.0.1:11434/v1"; $env:LLM_MODEL = "qwen2.5:7b"; $env:EMBEDDING_MODEL = "embeddinggemma"
```

Conviene escribir `127.0.0.1` y no `localhost`: en Windows `localhost` prueba primero IPv6 y cada llamada pierde unos 2 segundos. El cliente ya lo reemplaza solo.

Si el proveedor falla (red, clave, tiempo), el agente lo registra en la traza y sigue en modo offline. Una conexión rechazada falla enseguida y un servicio que falló no se vuelve a intentar durante 30 segundos. Una configuración inválida (proveedor desconocido, falta de modelo o de clave) termina con un mensaje claro y código de salida 2. Las consultas de más de 2000 caracteres se recortan.

## Medir el agente

```
python -m tiendahogar.evaluacion              # guardrail: reglas, reglas + n-gramas y reglas + embeddings (si hay)
python -m tiendahogar.evaluacion pedidos      # extracción de números de pedido e intención de consulta
python -m tiendahogar.evaluacion rag          # recuperación de documentos: BM25 contra híbrido
python -m tiendahogar.independiente medir     # lotes de frases escritas por otra persona, por origen
python -m tiendahogar.evaluacion --fallos     # además, lista los casos que fallan (se puede sumar a cualquiera)
python -m tiendahogar.rendimiento             # latencia por etapa: modelo de lenguaje, embeddings y código propio
python -m tiendahogar.rendimiento --sin-llm   # sin modelo de lenguaje
python -m tiendahogar.rendimiento --offline   # sin ningún modelo
```

Cada medición usa un conjunto de `tests/data/` dividido en desarrollo y prueba. Sin `EMBEDDING_MODEL` solo se miden las variantes sin red. Los resultados y sus salvedades están en los ADR [0003](docs/adr/0003-guardrail-en-tres-capas.md), [0004](docs/adr/0004-rag-hibrido-y-umbral-por-margen.md), [0011](docs/adr/0011-estrategia-de-evaluacion.md) y [0012](docs/adr/0012-rendimiento-y-respaldo-offline.md).

## Estructura

```
src/tiendahogar/   código del agente (solo librería estándar); data/ trae los 5 documentos sin editar
tests/             pytest: RAG, tool, guardrails, montos, lugares, sesión, preguntas mixtas y escenarios de punta a punta
docs/              arquitectura.md y adr/ (registro de decisiones)
SUBMISSION.md      la entrega con la plantilla del enunciado
```

La descripción de cada módulo está en [docs/arquitectura.md](docs/arquitectura.md). Las trazas de `python -m tiendahogar` se guardan en `trazas/trazas.jsonl` (ignorada por git) y no incluyen el texto de las consultas.

## Limitaciones

Están detalladas en [SUBMISSION.md](SUBMISSION.md). Las principales: el agente trabaja en español, los clientes de modelo no se probaron contra la API de un proveedor comercial, la memoria se limita al lugar, el monto y el número de pedido, y las cifras de medición salen de conjuntos de frases escritos por el mismo autor del código o ajustados mirándolos.
