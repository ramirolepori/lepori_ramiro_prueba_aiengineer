# ADR 0009: Modelos locales, clientes sin SDK, rendimiento y respaldo offline

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El enunciado permite OpenAI, Anthropic, Azure OpenAI o un modelo local, y no se sabe cuál usará el evaluador. El desarrollo no puede depender de una clave de pago, y el agente no puede quedar inutilizable o lento cuando un servicio de modelos falla. La latencia de una respuesta mezcla la de los modelos (que depende de la máquina) con la de la herramienta; solo esta última se expone y se optimiza.

## Decisión

- Se diseña contra la clase de modelo más usada por costo y calidad: los modelos chicos comerciales ("mini", "flash", "haiku") y, en local, uno abierto de 7 a 8 mil millones de parámetros. Referencia: `qwen2.5:7b` para redactar y `embeddinggemma` para embeddings, ambos en Ollama.
- Clientes HTTP propios con la librería estándar (`llm.py`, `embeddings.py`), sin SDK: uno compatible con OpenAI (sirve también para Ollama; se cambia con `LLM_BASE_URL`, `LLM_MODEL` y `LLM_API_KEY`) y uno para Anthropic. El de OpenAI reintenta con `max_completion_tokens` si un modelo rechaza `max_tokens`. Todo por variables de entorno, sin claves en el repositorio.
- Ollama con `127.0.0.1` y no `localhost`: en Windows `localhost` prueba primero IPv6 y cada llamada perdía unos 2 segundos (con `127.0.0.1`, 44 ms). El cliente lo reemplaza solo.
- Respaldo offline completo: sin proveedor, o si falla, el guardrail pasa a n-gramas, la recuperación a BM25 y la respuesta cita el documento. Una conexión rechazada falla enseguida y un servicio que acaba de fallar no se reintenta durante 30 segundos, así que un servidor caído no ralentiza cada pregunta.
- Cada respuesta trae `tiempos` por etapa y por balde (modelo de lenguaje, embeddings, código propio), también en la traza. `python -m tiendahogar.rendimiento` los mide. Los vectores se guardan normalizados, el guardrail y el recuperador comparten el cliente de embeddings (una llamada por pregunta) y los embeddings de los textos fijos se piden juntos y se guardan en `.cache/` (nunca preguntas de clientes).
- Una consulta de más de 2000 caracteres se recorta y la traza no guarda el texto del cliente.

## Alternativas descartadas

- `qwen2.5:3b`: respondió mal la pregunta que mezcla garantía y devolución (en 7 preguntas de prueba, no es una medición).
- `bge-m3` para embeddings: ver el ADR 0003.
- Los SDK de OpenAI y Anthropic: son dos llamadas HTTP y obligarían al evaluador a instalarlos.
- Reintentar siempre ante un fallo: con un servidor caído una sola pregunta tardaba muchos segundos.

## Evidencia

Sin ningún modelo, la herramienta responde en 2 ms de mediana; con embeddings y sin modelo de lenguaje, en 66 ms (60 de embeddings). El arranque en frío con embeddings es de 123 ms con la caché de disco (3,9 s sin ella). Con 1 a 32 clientes simultáneos y sin modelos, 0 errores y respuestas idénticas a las de un cliente solo, a unas 1.100 por segundo (al medir se corrigieron un contador de tiempo y una escritura de trazas compartidos entre hilos). Con embeddings, lo que limita es el servicio de embeddings. No medí varios clientes contra un mismo modelo de lenguaje.

Los clientes se probaron contra un servidor local que imita cada API (`tests/test_llm.py`) y de punta a punta con Ollama, no contra un proveedor comercial; está declarado en las limitaciones.
