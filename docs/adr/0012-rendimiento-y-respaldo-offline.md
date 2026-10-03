# ADR 0012: Rendimiento por etapa y respaldo offline

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

La latencia de una respuesta depende de dos cosas distintas: los modelos (el de lenguaje que redacta y el de embeddings, que cambian con el modelo y el hardware) y la herramienta (guardrail, recuperación, tool de pedidos, validación), donde sí hay que optimizar. Mezclarlas lleva a optimizar lo que no se puede cambiar. Además, el agente no puede quedar inutilizable o lento cuando un servicio de modelos falla.

## Decisión

- Cada respuesta trae `tiempos` con tres baldes (modelo de lenguaje, modelo de embeddings y código propio) y el tiempo de cada etapa (`tiempos.py`). Quedan también en la traza. `python -m tiendahogar.rendimiento` mide 16 preguntas representativas (política, pedidos, derivaciones, mixtas y fuera de alcance) en tres modos: sin ningún modelo (`--offline`), con embeddings y sin modelo de lenguaje (`--sin-llm`) y completo. Hardware de las pruebas: una PC con Windows, 15,8 GB de RAM y sin GPU, con Ollama.
- La herramienta se optimiza donde está el costo propio. Los vectores se guardan normalizados y la similitud es un producto punto; los puntajes de cada oración se recuerdan para que el guardrail y la intención de pedido no los calculen dos veces; si las reglas ya derivan una pregunta de una sola cláusula no se consulta al modelo de embeddings; una pregunta con número de pedido no evalúa la intención. Una pregunta normal hace una sola llamada de embeddings, porque el guardrail y el recuperador comparten el cliente.
- Arranque en frío: los embeddings de los textos fijos (documentos, preguntas fuera de alcance y frases de ejemplo del guardrail) se piden en una sola llamada y se guardan en disco (`.cache/`, ignorada por git; nunca se guardan preguntas de clientes).
- Ollama con `127.0.0.1` y no `localhost`: en Windows `localhost` prueba primero IPv6 mientras el servidor escucha en IPv4, y cada llamada perdía unos 2 segundos. Con `127.0.0.1` tarda 44 ms (47 veces menos). El cliente HTTP reemplaza `localhost` y vuelve a la dirección original si el servidor no responde.
- Respaldo offline completo: sin proveedor configurado, o si falla, el guardrail pasa a n-gramas de caracteres, la recuperación a BM25 y la respuesta cita el documento. Una conexión rechazada falla enseguida, sin reintentos, y un servicio que acaba de fallar no se vuelve a intentar durante 30 segundos (corte de circuito), así que un servidor caído no ralentiza cada pregunta. La detección de la conexión rechazada usa el tipo de excepción y no el texto del mensaje, que depende del idioma del sistema.
- Entradas: una consulta vacía pide la consulta, y una de más de 2000 caracteres se recorta (queda un evento en la traza) para no trabajar ni pedir embeddings sobre textos enormes.
- La traza no guarda el texto del cliente (en las preguntas mixtas guarda solo la cantidad de cláusulas).

## Alternativas descartadas

- Optimizar el modelo de lenguaje: depende del modelo y del hardware, no de este código.
- Reintentar siempre ante un fallo: con un servidor caído una sola pregunta tardaba 9 segundos (solo modelo de lenguaje) y hasta 37 (con embeddings).
- Un tope de tokens para acelerar: no aportó nada (ADR 0010).

## Consecuencias

La herramienta, sin contar al modelo de lenguaje, responde en decenas de milisegundos con embeddings y en unos pocos sin ningún modelo. Con el modelo de lenguaje local en CPU, el modelo explica casi todo el tiempo, y las colas se deben a la carga del modelo en memoria (la primera pregunta puede tardar decenas de segundos, evitable con `OLLAMA_KEEP_ALIVE`) y a respuestas largas.

## Evidencia

Medición inicial, herramienta con embeddings y sin modelo de lenguaje: 2129 ms de mediana por pregunta nueva, 2102 ms del servicio de embeddings y 33 ms de código propio; arranque en frío de 12,5 s. Después de los cambios de arriba, mediana por pregunta nueva, en milisegundos:

| Modo | Total | Modelo de lenguaje | Modelo de embeddings | Código propio |
| --- | --- | --- | --- | --- |
| Sin ningún modelo (reglas, n-gramas y BM25) | 2,0 | 0 | 0 | 2,0 |
| Herramienta con embeddings, sin modelo de lenguaje | 66 | 0 | 60 | 6,6 |
| Completo, con `qwen2.5:7b` local en CPU (las 16 preguntas) | 127 | 0 | 75 | 10 |

En el modo completo la mediana es baja porque 9 de las 16 preguntas no llaman al modelo de lenguaje (derivaciones, pedidos, envíos con lugar y fuera de alcance, resueltas por código). Las 7 que sí lo llaman tardan de 15 a 33 segundos, con una mediana de 16,7 segundos, y el modelo de lenguaje explica más del 99 % de ese tiempo: es la generación en CPU (unos 3 tokens por segundo) y no el código del agente.

Arranque en frío con embeddings: 123 ms con la caché de disco (sin ella, 3,9 s).

Prueba del CLI desde un clon limpio, sin `.env` y con el Python del sistema: sin configuración corre en modo offline y responde en unos 0,3 s por pregunta. Se probaron 13 preguntas representativas, el chat interactivo y casos límite (caracteres nulos y de control, emoji, texto mal codificado, cierre de la entrada estándar, proveedor desconocido y modelo o clave faltante, con mensaje claro y código de salida 2), sin errores.
