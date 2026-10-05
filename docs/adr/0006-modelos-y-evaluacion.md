# ADR 0006: Modelos locales, respaldo offline y estrategia de evaluación

Estado: aceptada. Octubre de 2026.

## Modelos y respaldo

El enunciado permite OpenAI, Anthropic, Azure OpenAI o un modelo local, y no se sabe cuál usará el evaluador.

- Se diseña contra un modelo chico (referencia: `qwen2.5:7b` para redactar y `embeddinggemma` para embeddings, ambos en Ollama). `qwen2.5:3b` respondió peor la pregunta que mezcla garantía y devolución.
- Clientes HTTP propios con la librería estándar (`llm.py`, `embeddings.py`), sin SDK: uno compatible con OpenAI (sirve también para Ollama y otros) y uno para Anthropic. Todo por variables de entorno, sin claves en el repositorio.
- Respaldo offline completo: sin proveedor, o si falla, el guardrail usa n-gramas, la recuperación BM25 y la respuesta cita el documento. Una respuesta malformada del proveedor o cualquier error del cliente de modelo cae al modo offline. Un servicio que falla no se reintenta durante 30 segundos.
- Ollama con `127.0.0.1` y no `localhost`: en Windows `localhost` prueba primero IPv6 y cada llamada perdía unos 2 segundos.
- Cada respuesta trae `tiempos` por etapa. Los embeddings de textos fijos se guardan en `.cache/` (nunca preguntas de clientes) y la memoria de preguntas tiene tope. Sin modelos la herramienta responde en 2 ms de mediana; con embeddings, en 66 ms.
- Los clientes se probaron contra un servidor local que imita cada API y de punta a punta con Ollama, no contra un proveedor comercial.

## Evaluación

Un agente que se ajusta mirando las mismas frases con las que se mide da cifras optimistas.

- Conjuntos propios (`tests/data/`) divididos en desarrollo (para ajustar) y prueba (sin tocar), medidos con `python -m tiendahogar.evaluacion`.
- Lotes independientes de frases ajenas (`python -m tiendahogar.independiente medir`). La primera medición de un lote es la limpia; después de corregir sus fallos pasa a ser optimista y la prueba vuelve a ser un lote nuevo. Las correcciones son reglas generales, no frases copiadas.
- La única medición limpia es el lote 3 (42 frases, medido una vez antes de tocar nada). Con embeddings: riesgo 8 de 10 con 0 falsos positivos en 29, números de pedido 5 de 5, documentos 15 de 15 y ajenas rechazadas 8 de 8. Sin embeddings, el riesgo daba 5 y 6 de 10. Sus fallos (un identificador raro, quejas dichas de otra forma, agradecimientos, lugares) se corrigieron con reglas generales.
- Una revisión externa y dos rondas de búsqueda de errores encontraron defectos que los tests propios no veían (un "5-10 días" leído como $5, montos escritos como "medio millón", datos sensibles en las trazas, respuestas rotas del proveedor). Cada uno tiene su test en `tests/test_regresiones_revision.py`.
