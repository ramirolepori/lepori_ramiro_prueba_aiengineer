## Arquitectura propuesta y justificación

```
cliente ── pregunta (y, si hay, una sesión) ──► AgenteSoporte.responder
  1. inyección de prompt evidente ─────────────► rechazo, sin modelo
  2. guardrail (reglas + similitud semántica) ─► derivación a soporte@tiendahogar.example, sin modelo
       reembolso de más de $500, queja de trato, disputa de facturación, tema legal,
       incidente de seguridad con un producto
       pregunta mixta: antes se responde la parte permitida
  3. pedidos: ORD-XXXX, "pedido 1001", "n°2000" ► consultar_estado_pedido (tabla mock)
  4. RAG híbrido (embeddings + BM25) con umbral ► documentos relevantes
       ninguno ni pedido ─► "no tengo esa información" (o pide el número de pedido)
  5. envíos: el lugar decide el plazo (código) ─► capital, otras ciudades o exterior
  6. redacción: modelo con SOLO ese contexto │ sin modelo: cita los documentos
  7. validación de la salida y notas obligatorias agregadas por código ─► Respuesta
```

El flujo lo decide el código y el modelo solo redacta con lo recuperado. Lo que el enunciado trata como regla (derivar, no inventar datos, no aprobar reembolsos) corre antes o después del modelo, así que el comportamiento crítico es el mismo con cualquier modelo, también uno chico y local, y se prueba sin red. Sin modelo configurado el agente funciona completo en modo offline. Una sesión opcional recuerda qué dato falta (lugar, monto, número de pedido, hace cuánto compró) y lo repregunta en vez de volcar un documento entero: con "quiero hacer una devolución" pide el número de pedido, consulta la tool y sigue con la cuenta del plazo sin perder el hilo.

Trade-offs por el límite de tiempo y por lo que los documentos no dicen:
- Sin framework de agentes ni tool calling decidido por el modelo: con 5 documentos, una tool y un flujo lineal agrega capas, y un modelo chico se equivoca justo en los casos críticos ([ADR 0001](docs/adr/0001-alcance-y-orquestacion.md)).
- Guardrail en tres capas (reglas, embeddings y n-gramas como respaldo sin red); el modelo generativo no clasifica ([ADR 0002](docs/adr/0002-guardrail-y-robustez.md)).
- Decisiones mías donde los documentos callan: hasta $500 el agente informa la política sin prometer la aprobación, y "la capital" es la Ciudad de Buenos Aires ([ADR 0004](docs/adr/0004-reglas-donde-los-documentos-callan.md)).
- Después de generar, el código valida la salida (cifras, correos y promesas inventados) y agrega las aclaraciones obligatorias.

Las decisiones con sus alternativas y su evidencia están en [docs/adr](docs/adr/README.md), y los módulos y cómo extender el agente en [docs/arquitectura.md](docs/arquitectura.md).

## Decisiones técnicas de RAG

- Chunking: no. Cada documento tiene menos de 400 caracteres y es una sola política, y partirlo separaría frases que se necesitan juntas (la regla de devoluciones y su excepción). Cada documento es un fragmento y el recuperador mide la similitud del documento entero y de cada oración. Con miles de documentos usaría `rag.dividir`: fragmentos de unos 600 caracteres alineados a títulos, con documento y sección como metadato.
- Embeddings: `embeddinggemma` (multilingüe, corre local en Ollama), pedido por HTTP a `/v1/embeddings`, que también exponen OpenAI y otros. Entiende paráfrasis y faltas que BM25 no ve. BM25 queda al lado como respaldo si el proveedor falla y para correr sin red ni claves ([ADR 0003](docs/adr/0003-recuperacion-y-pedidos.md)).
- Threshold: no usé un número absoluto de similitud, porque cada modelo de embeddings tiene su escala. Un documento es relevante si supera por 0,08 a la mayor similitud con las preguntas fuera de alcance de `data/fuera_de_alcance.json`, o si BM25 lo considera relevante, y se usan hasta 3. Si ninguno lo supera y no hay un pedido, el agente responde "no tengo esa información en nuestras políticas" sin llamar al modelo. Con 122 preguntas (desarrollo y prueba) el híbrido recupera el documento correcto en 67 de 70 y 30 de 32, y de un banco de 75 preguntas ajenas al negocio rechaza 73.

## Pruebas automatizadas

Comando exacto: `python -m pytest tests/` (o `pytest tests/` si pytest ya está instalado). Son 1045 tests que corren en unos 25 segundos, sin red ni `.env`, en modo offline. Hay dos opt-in que necesitan Ollama (`TIENDAHOGAR_TEST_OLLAMA=1`).

Lo primero que hay que leer es `tests/test_criticos.py`: los tres casos críticos del enunciado y los límites ($500 no escala y $501 sí, liquidación, pedido inexistente). El resto:
- Recuperación: `test_rag.py` y `test_recuperador.py`. Tool de pedidos: `test_pedidos.py` y `test_pedidos_flexibles.py` (inexistentes o mal formados dan "No encontrado", sin inventar).
- Guardrail: `test_guardrails.py` y `test_semantica.py` (reembolsos, formatos de monto, quejas, facturación, temas legales, paráfrasis e inyección).
- Escenarios y ataques: `test_agente.py`, `test_mixtas.py`, `test_fuera_de_alcance.py` y `test_adversarial.py` (75 preguntas ajenas y 75 intentos de sacar al agente de su alcance; ninguno se obedece).
- Conversación y lugares: `test_sesion.py` y `test_lugares.py`. Clientes de modelo: `test_llm.py`, contra un servidor local que imita cada API.
- Errores encontrados por una revisión externa: `test_regresiones_revision.py`.

Hay además mediciones sobre conjuntos de frases (`python -m tiendahogar.evaluacion` y `python -m tiendahogar.independiente medir`). Con embeddings el guardrail detecta el 98,9 % del riesgo en desarrollo y el 97,6 % en prueba, con 0 falsos positivos, pero esas cifras son optimistas porque el conjunto lo escribí yo. La cifra honesta es la de un lote de 42 frases medido una sola vez antes de tocar nada: 8 de 10 en riesgo con 0 falsos positivos en 29 (5 o 6 de 10 sin embeddings) ([ADR 0006](docs/adr/0006-modelos-y-evaluacion.md)).

## Cómo mapearías esto a producción

- Microsoft Foundry: el agente pasa a ser un agente de Foundry con el modelo desplegado ahí. `consultar_estado_pedido` se registra como tool (function calling) y las reglas de escalamiento quedan como capa previa en código, más Content Safety y Prompt Shields. Las trazas se reemplazan por la telemetría y las evaluaciones de Foundry.
- Databricks y Unity Catalog: los documentos se publican como tablas gobernadas con un índice de Mosaic AI Vector Search. El recuperador se cambia por una consulta híbrida a ese índice, manteniendo la interfaz `buscar` y el umbral por margen.
- Apigee: el agente se expone con autenticación, cuotas y auditoría. La tool de pedidos llama a la API real por el mismo gateway, con el usuario autenticado para que solo vea sus pedidos, y esa API aporta el valor real de la compra para la regla de los $500.
- Kafka: las derivaciones a un humano se publican como evento (por ejemplo `soporte.escalamientos`) y un consumidor crea el caso. Los eventos de cada conversación salen también hacia observabilidad y evaluación continua.
- Estado de la conversación: hoy la sesión es un objeto en memoria. En producción vive en un almacén por conversación con vencimiento, y el lugar sale de la dirección de entrega.
- Además: secretos en un gestor, datos personales redactados antes de registrar y evaluación en CI con preguntas reales anonimizadas.

## Limitaciones conocidas

- Trabaja solo en español. El enunciado no pide otros idiomas, así que las preguntas en inglés caen en "no tengo esa información" y no se cubren.
- Los clientes de modelo (`OpenAICompatible` y `Anthropic`) se probaron contra un servidor local que imita cada API y de punta a punta con `qwen2.5:7b` y `embeddinggemma` en Ollama. No los probé contra la API de un proveedor comercial.
- Las cifras salen de conjuntos de frases que escribí yo o que se ajustaron mirándolos; un lote ajeno puede dar peor. La detección de inyección se limita a lo inequívoco y la validación de la salida del modelo es una red de seguridad, no una garantía.
- Decisiones propias que los documentos no dan: hasta $500 el agente no deriva ni promete la aprobación; el tope se aplica por reembolso y no a la suma de varios; "la capital" es la Ciudad de Buenos Aires; el monto es el que declara el cliente porque la tabla no tiene precios; un incidente de seguridad con un producto se deriva a una persona (quinta categoría, solo por reglas).
- El diccionario de lugares es una muestra: un lugar que no figura se confirma con el cliente.
- La memoria cubre datos pendientes (lugar, monto, pedido, fecha de compra), no sigue la charla (un "y la de una licuadora?" sin contexto se responde como pregunta nueva) y vive en el proceso.
- El RAG a veces recupera solo uno de dos documentos en preguntas que los mezclan y falla en paráfrasis lejanas. En modo offline, una pregunta fuera de tema que comparte una palabra del dominio recibe el documento completo.
- Varias consultas a la vez: sin modelos, 32 clientes simultáneos dan las mismas respuestas que uno solo, sin errores. No medí varios clientes contra un mismo modelo de lenguaje.
- Los documentos no dicen precios, marcas ni garantía extendida: el agente responde que no tiene esa información.
- Los tests y las mediciones se corrieron en Windows con Python 3.11.

## Tiempo invertido

Aproximadamente 16 horas.
