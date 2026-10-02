## Arquitectura propuesta y justificación

```
cliente
  │
  ▼
┌───────────────────────────── AgenteSoporte.responder ─────────────────────────────┐
│ 1. detectar_inyeccion ──sí──► rechazo (sin LLM)                                   │
│ 2. guardrails.evaluar ──sí──► derivación a soporte@tiendahogar.example (sin LLM)  │
│ 3. ORD-XXXX en el texto ──► consultar_estado_pedido (tabla mock)                  │
│ 4. RAG (BM25 + umbral) ──► fragmentos relevantes                                  │
│        sin fragmentos ni pedido ──► "no tengo esa información" (sin LLM)          │
│ 5. redacción: LLM con SOLO ese contexto  │  sin LLM: cita los documentos tal cual │
│ 6. traza JSONL de cada paso                                                       │
└────────────────────────────────────────────────────────────────────────────────────┘
```

Lo que el enunciado trata como regla (escalar reembolsos mayores a $500, quejas de trato, disputas de facturación y temas legales; no inventar datos) lo resuelve código determinístico que corre antes del modelo. El LLM solo redacta con lo recuperado. Así el comportamiento crítico es el mismo con cualquier modelo, incluido uno chico y local, y se puede probar con tests sin red.

Trade-offs por el tiempo:
- No hay un bucle de tool calling decidido por el modelo. El agente detecta los números de pedido con una expresión regular y llama a la tool siempre. Es más predecible y más barato, pero no cubre pedidos mencionados sin el formato `ORD-XXXX` (el agente pide el número).
- Los guardrails son reglas y expresiones regulares en español. Son rápidas, auditables y probadas, pero no entienden cualquier paráfrasis. Está previsto sumar un clasificador (ver producción), sin quitar las reglas.
- Sin LLM el agente responde citando el documento completo: es correcto, pero menos natural. Con LLM, la redacción no se verificó contra una API real (ver limitaciones).

## Decisiones técnicas de RAG

- Chunking: no. Cada documento tiene menos de 400 caracteres y es una sola política; partirlo separaría frases que se necesitan juntas (por ejemplo la regla de devoluciones y su excepción). `rag.dividir` ya parte por párrafos con solape y es lo que usaría si el corpus creciera: fragmentos de unos 600 caracteres alineados a títulos y párrafos, con el nombre del documento y la sección como metadato, y un recuperador híbrido (BM25 más embeddings) con reordenamiento de los mejores resultados.
- Embeddings: ninguno. Usé BM25 porque con 5 documentos cortos recuperar por palabras funciona y es explicable, no necesita clave ni red y los tests son determinísticos. Para cubrir sinónimos agregué normalización de tildes, plurales simples y una tabla corta de conceptos (por ejemplo "devolver" y "devolución", "enviar" y "envío"). Con miles de documentos pasaría a embeddings (por ejemplo `text-embedding-3-small` o un modelo multilingüe como `multilingual-e5`, a decidir con una evaluación de recuperación sobre preguntas reales).
- Umbral: se devuelven hasta 3 fragmentos con puntaje BM25 >= 1,5 y >= 50 % del mejor. Además, una coincidencia con una sola palabra que no es un concepto del dominio (por ejemplo "capital" en "capital de Francia") no cuenta. Se calibró a mano con preguntas dentro y fuera de alcance (`tests/test_rag.py`). Si ningún documento supera el umbral y no hay pedido, el agente responde que no tiene esa información y no llama al modelo. Con embeddings el umbral sería de similitud coseno, calibrado con un conjunto de preguntas etiquetadas.

## Pruebas automatizadas

Comando: `python -m pytest tests/` (o `pytest tests/`).

- `test_rag.py`: una pregunta de garantía trae el documento de garantía, preguntas de cada documento, garantía mezclada con devolución trae ambos documentos y preguntas fuera de alcance no superan el umbral.
- `test_pedidos.py`: los cuatro pedidos válidos, ids inexistentes o mal formados que devuelven "No encontrado" sin inventar producto ni fecha, y extracción de ids del texto.
- `test_guardrails.py`: reembolsos de $501 o más escalan, el de exactamente $500 no, "600 días" no se toma como dinero, quejas de trato, disputas de facturación, temas legales, varias categorías a la vez, formatos de monto e inyección de prompt.
- `test_agente.py`: escenarios de punta a punta (garantía, producto en liquidación, garantía con devolución, pedido existente, pedido inexistente, pedido sin número, fuera de alcance, reembolso de $500 y de $501), que el modelo no se llama cuando salta un guardrail, que el prompt solo lleva el contexto recuperado, el respaldo offline si el LLM falla y las trazas.
- `test_llm.py`: los clientes OpenAI-compatible y Anthropic contra un servidor local (formato del pedido, clave, reintento con `max_completion_tokens`, errores y el agente de punta a punta con un proveedor).

## Cómo mapearías esto a producción

- Microsoft Foundry: el agente pasa a ser un agente de Foundry con el modelo desplegado ahí. `consultar_estado_pedido` se registra como tool (function calling) y las reglas de escalamiento se mantienen como una capa previa en código, más Content Safety y Prompt Shields para inyección. Las trazas JSONL se reemplazan por la telemetría y las evaluaciones de Foundry.
- Databricks / Unity Catalog: los documentos se publican como tablas gobernadas en Unity Catalog, con un índice de Mosaic AI Vector Search (o el índice que defina el equipo) sincronizado con la tabla. El recuperador actual se cambia por una consulta híbrida a ese índice, manteniendo la misma interfaz `buscar`, el umbral y el reordenamiento. El control de acceso lo da Unity Catalog.
- Apigee: el agente se expone detrás de Apigee con autenticación, cuotas, límite de uso y registro de auditoría. La tool de pedidos deja de ser una tabla mock y llama a la API real de pedidos a través del mismo gateway, con el usuario autenticado para que solo vea sus pedidos.
- Kafka: las derivaciones a un humano se publican como evento (por ejemplo un tema `soporte.escalamientos`) en vez de depender de que el cliente escriba un correo, y un consumidor crea el caso en la herramienta de soporte. Los eventos de cada conversación (traza, costo, resultado) también salen por Kafka hacia observabilidad y evaluación continua.
- Además: secretos en un gestor (no en `.env`), conversaciones con memoria por sesión, redacción de datos personales antes de registrar y un conjunto de evaluación en CI con preguntas reales anonimizadas.

## Limitaciones conocidas

- Los clientes de LLM (`OpenAICompatible` y `Anthropic` en `llm.py`) se probaron contra un servidor HTTP local que imita la forma de cada API (`tests/test_llm.py`), incluido el rechazo de `max_tokens` que hacen algunos modelos de OpenAI. [Completar con el proveedor real que se haya probado, por ejemplo Gemini por su endpoint compatible. Lo que no se haya probado contra la API real queda declarado acá.]
- Los guardrails son reglas en español. No cubren paráfrasis raras, otros idiomas ni ironía. Un monto escrito de forma rara (por ejemplo "quinientos cincuenta") se detecta solo para unos pocos casos. Un reembolso sin monto explícito no escala: el agente informa la política y la regla de los $500, y nunca aprueba nada.
- Una devolución de un producto de más de $500 mencionada como "devolver una estufa de $900" se escala por prudencia aunque el cliente no use la palabra reembolso. Es una decisión mía, no está en los documentos.
- La tabla de conceptos del RAG y el umbral se ajustaron a mano con pocas preguntas. Con preguntas reales habría que medir y reajustar. En modo offline una pregunta fuera de tema que comparta un concepto con un documento (por ejemplo "cuánto cuesta el envío") recibe el documento de envíos completo, no la respuesta exacta.
- No hay memoria entre mensajes: cada pregunta se trata sola. Si el cliente da el número de pedido en un mensaje y pregunta en otro, el agente no los une.
- Los documentos no dicen precios, marcas, garantía extendida ni qué pasa con un reembolso de más de $500 más allá de la aprobación del supervisor. El agente dice que no tiene esa información.
- La salida del modelo no se valida después de generarla (por ejemplo citas o montos inventados). El prompt limita lo que puede usar y el contexto es corto, pero no hay una segunda verificación.
- Los tests se corrieron en Windows con Python 3.11.

## Tiempo invertido

[Completar: horas aproximadas]
