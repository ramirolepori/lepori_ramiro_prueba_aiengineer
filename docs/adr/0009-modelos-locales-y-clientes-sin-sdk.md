# ADR 0009: Modelos locales de referencia y clientes HTTP sin SDK

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El enunciado permite OpenAI, Anthropic, Azure OpenAI o un modelo local. No se sabe qué proveedor usará el evaluador, y el desarrollo no puede depender de una clave de pago. Cuanto mejor es el modelo, menos defensas necesita el código, así que hay que elegir contra qué clase de modelo se diseña.

## Decisión

- Principio de elección: no se apunta a un modelo de última generación (no es lo que se usaría en un soporte de este tipo por costo) ni a uno viejo (obligaría a sobreajustar el código). Se apunta a la clase de modelos más usada por su relación costo y calidad: los modelos chicos de los proveedores comerciales (las gamas "mini", "flash" o "haiku") y, en local, un modelo abierto de 7 a 8 mil millones de parámetros.
- Referencia local: `qwen2.5:7b` para redactar y `embeddinggemma` (622 MB, multilingüe) para embeddings, ambos en Ollama. Si el agente funciona bien con ese modelo, que es de una clase igual o inferior a los chicos comerciales, debería funcionar con uno de esa gama.
- Clientes propios con la librería estándar (`llm.py`, `embeddings.py`), sin SDK: un cliente compatible con la API de OpenAI (sirve también para Ollama y cualquier servidor compatible, cambiando `LLM_BASE_URL`, `LLM_MODEL` y `LLM_API_KEY`) y uno para Anthropic. El cliente de OpenAI reintenta con `max_completion_tokens` cuando un modelo de razonamiento rechaza `max_tokens`. Los embeddings se piden al endpoint `/v1/embeddings`.
- Ollama se usa con `127.0.0.1` y no `localhost`: en Windows `localhost` prueba primero IPv6 y cada llamada perdía unos 2 segundos (ADR 0012). El cliente reemplaza `localhost` solo.
- La configuración es por variables de entorno, sin claves en el repositorio (`.env.example` y `.env` ignorado por git). Sin configuración el agente corre en modo offline.

## Alternativas descartadas

- `qwen2.5:3b`: en 7 preguntas de prueba respondió mal la que mezcla garantía y devolución (45 días con falla) y enredó la de una licuadora de 8 meses; el 7B respondió bien las 7. Es una prueba chica, no una medición.
- `bge-m3` (1,2 GB) para embeddings: ver ADR 0003.
- Los SDK de OpenAI y Anthropic: agregan dependencias para algo que son dos llamadas HTTP y obligan al evaluador a instalarlas.
- Gemini como proveedor: es compatible con el cliente de OpenAI, pero se eligió local porque es la opción que menciona el enunciado.

## Consecuencias

El agente corre en una máquina sin GPU ni claves, y cambiar de proveedor es cambiar variables de entorno. Los clientes se probaron contra un servidor HTTP local que imita la forma de cada API (`tests/test_llm.py`); no se probaron contra la API de un proveedor comercial, y está declarado en las limitaciones.
