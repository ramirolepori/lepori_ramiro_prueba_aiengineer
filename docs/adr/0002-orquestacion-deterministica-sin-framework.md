# ADR 0002: Orquestación determinística, sin framework

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El enunciado pide un agente que responda con RAG, use una tool de pedidos y tenga un guardrail que derive ciertos casos a una persona. Hay que decidir quién gobierna el flujo: el modelo de lenguaje (con tool calling y un framework de agentes) o el código.

## Decisión

El código decide el flujo y el modelo de lenguaje solo redacta con lo recuperado:

1. Detección de inyección de prompt en la entrada.
2. Guardrail de escalamiento.
3. Tool de pedidos.
4. Recuperación de documentos (RAG).
5. Redacción, con modelo de lenguaje o, sin él, citando los documentos.
6. Validación de la salida y notas obligatorias agregadas por código.

Todo lo que el enunciado trata como regla (derivar, no inventar, no aprobar reembolsos) lo resuelve código que corre antes o después del modelo. No se usa LangChain, LangGraph ni un bucle de tool calling decidido por el modelo.

## Alternativas descartadas

- LangChain o LangGraph. Con 5 documentos, una tool y un flujo lineal agregarían capas que esconden lo que se quiere mostrar y dependencias que instalar. Serían razonables si el corpus o las tools crecen mucho, con flujos con ramas, estado o varios agentes. Para el despliegue real el equivalente natural es el SDK de agentes de Microsoft Foundry (ver la sección de producción de `SUBMISSION.md`).
- Tool calling decidido por el modelo. Es menos predecible y más caro, y un modelo chico se equivoca justo en los casos que importan. El modelo local de 3 mil millones de parámetros falló en preguntas que mezclan garantía y devolución, así que lo crítico no puede depender de él.

## Consecuencias

- El comportamiento crítico es el mismo con cualquier modelo, también uno chico y local, y se prueba con tests sin red.
- Hay un modo offline completo (reglas, n-gramas de caracteres y BM25) cuando no hay modelo configurado o el proveedor falla (ver ADR 0012).
- Cada decisión del flujo queda en una traza JSONL, que sirve para depurar y para medir.
- Costo: el agente no se adapta solo a un caso nuevo. Cada capacidad nueva (por ejemplo los lugares de envío o la memoria) se agrega como código y se prueba.
