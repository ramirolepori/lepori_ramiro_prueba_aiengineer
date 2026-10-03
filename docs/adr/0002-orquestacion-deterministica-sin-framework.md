# ADR 0002: Orquestación determinística y modelo que solo redacta

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Hay que decidir quién gobierna el flujo: el modelo de lenguaje (con tool calling y un framework de agentes) o el código. Las pruebas con `qwen2.5:7b` mostraron que un modelo chico omite aclaraciones obligatorias, deforma cifras, inventa citas, cubre una sola de dos políticas y razona mal cuentas simples (el plazo de 30 días). Con `qwen2.5:3b` fue peor en los casos que importan.

## Decisión

El código decide el flujo y el modelo solo redacta con lo recuperado: inyección de prompt, guardrail, tool de pedidos, RAG, redacción y validación de la salida. No se usa LangChain, LangGraph ni un bucle de tool calling decidido por el modelo.

Lo obligatorio lo resuelve código antes o después del modelo:
- El modelo recibe solo documentos y pedidos recuperados y un prompt breve que le prohíbe prometer aprobaciones.
- Validación de la salida: se descarta (y se usa el modo offline) una respuesta con cifras o correos que no estaban en el contexto, demasiado corta, o con cuatro o más palabras largas sin respaldo en el contexto (calibrado con respuestas reales; es una red de seguridad, no una garantía). Las citas se limpian.
- Notas, preguntas y respuestas por código, sin pasar por el modelo: la regla de los $500, el pedido del número de pedido, el plazo de devolución según los días desde la compra (`plazos.py`), el canal humano, el plazo de envío según el lugar y los agradecimientos.
- Cobertura: si la pregunta nombra dos políticas y el modelo cubrió una, el código agrega el texto de la otra con su cita.

## Alternativas descartadas

- LangChain o LangGraph: con 5 documentos, una tool y un flujo lineal agregan capas y dependencias. Serían razonables con un corpus o unas tools mucho mayores.
- Tool calling decidido por el modelo: es menos predecible y un modelo chico se equivoca justo en los casos críticos. El esquema de la tool está definido en `pedidos.py` por si se quiere exponer.
- Responder con la oración exacta del documento, sin modelo: no puede inventar pero le quita naturalidad.

## Consecuencias

El comportamiento crítico es el mismo con cualquier modelo y se prueba sin red. El modo offline es una salida válida. Cada decisión queda en una traza JSONL. Costo: cada capacidad nueva (lugares, memoria) es código que hay que probar.
