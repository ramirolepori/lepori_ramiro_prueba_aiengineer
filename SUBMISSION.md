## Arquitectura propuesta y justificación

```
cliente ── pregunta (y, si hay, una sesión) ──► AgenteSoporte.responder
  1. inyección de prompt evidente ─────────────► rechazo, sin modelo
  2. guardrail (reglas + similitud semántica) ─► derivación a soporte@tiendahogar.example, sin modelo
       reembolso de más de $500, queja de trato, disputa de facturación, tema legal
       pregunta mixta: antes se responde la parte permitida
  3. pedidos: ORD-XXXX, "pedido 1001", "n°2000" ► consultar_estado_pedido (tabla mock)
  4. RAG híbrido (embeddings + BM25) con umbral ► documentos relevantes
       ninguno ni pedido ─► "no tengo esa información" (o pide el número de pedido)
  5. envíos: el lugar decide el plazo (código) ─► capital, otras ciudades o exterior
  6. redacción: modelo con SOLO ese contexto │ sin modelo: cita los documentos
  7. validación de la salida y notas obligatorias agregadas por código ─► Respuesta
```

El flujo lo decide el código y el modelo de lenguaje solo redacta con lo recuperado. Lo que el enunciado trata como regla (derivar, no inventar datos, no aprobar reembolsos) corre en código antes o después del modelo. Así el comportamiento crítico es el mismo con cualquier modelo, también uno chico y local, y se prueba sin red. Sin modelo configurado el agente funciona completo en modo offline. Una sesión opcional recuerda qué dato le pidió al cliente (lugar, monto, número de pedido, antigüedad de la compra) y lo repregunta en vez de volcar un documento entero.

Trade-offs por el límite de tiempo y los datos que dan los documentos:
- Sin framework de agentes ni tool calling decidido por el modelo. Con 5 documentos, una tool y un flujo lineal, un framework agrega capas y un modelo chico se equivoca justo en los casos críticos. Sería razonable si el corpus y las tools crecen. [ADR 0002](docs/adr/0002-orquestacion-deterministica-sin-framework.md).
- Guardrail en tres capas: reglas (lo evidente), embeddings contra frases de ejemplo (paráfrasis y faltas de ortografía) y n-gramas como respaldo sin red. El modelo generativo no clasifica. [ADR 0003](docs/adr/0003-guardrail-en-tres-capas.md).
- Los documentos dejan huecos y los resolví con decisiones declaradas: hasta $500 el agente informa la política y no deriva, sin prometer la aprobación ([ADR 0006](docs/adr/0006-reembolsos-hasta-500.md)); "la capital" es la Ciudad de Buenos Aires y el plazo de envío lo decide el código según el lugar ([ADR 0007](docs/adr/0007-envios-segun-el-lugar.md)).
- Pedidos: se acepta el número escrito de varias formas, no se busca por nombre de producto y no se corrige en silencio un identificador raro. [ADR 0005](docs/adr/0005-consulta-de-pedidos-en-tres-capas.md).
- Después de generar, el código valida la salida (cifras o correos inventados) y agrega las aclaraciones obligatorias. [ADR 0002](docs/adr/0002-orquestacion-deterministica-sin-framework.md).
- Lo que no tiene que ver con la tienda no llega al modelo, y las órdenes de cambiar sus reglas se bloquean. [ADR 0011](docs/adr/0011-robustez-ante-intentos-de-sacarlo-de-alcance.md).

Todas las decisiones, con sus alternativas y su evidencia, están en [docs/adr](docs/adr/README.md). Los módulos y cómo extender el agente, en [docs/arquitectura.md](docs/arquitectura.md).

## Decisiones técnicas de RAG

- Chunking: no. Cada documento tiene menos de 400 caracteres y es una sola política, y partirlo separaría frases que se necesitan juntas (la regla de devoluciones y su excepción). Cada documento es un fragmento y el recuperador mide la similitud del documento entero y de cada oración. Con un corpus de miles de documentos usaría `rag.dividir`: fragmentos de unos 600 caracteres alineados a títulos, con el documento y la sección como metadato.
- Embeddings: `embeddinggemma` (multilingüe, corre local en Ollama), pedido por HTTP a `/v1/embeddings`, que también exponen OpenAI y otros. Entiende paráfrasis y faltas que BM25 no ve. BM25 se mantiene al lado por tres razones: es el respaldo si el proveedor falla, permite correr sin red ni claves, y la fusión de ambas señales es más robusta que cualquiera sola. [ADR 0004](docs/adr/0004-rag-hibrido-y-umbral-por-margen.md).
- Threshold: no usé un número absoluto de similitud, porque cada modelo de embeddings tiene su escala. Un documento es relevante si supera por 0,08 a la mayor similitud con las preguntas fuera de alcance de `data/fuera_de_alcance.json`, o si BM25 lo considera relevante. Se ordenan por fusión de posiciones y se usan hasta 3. Si ninguno supera el umbral y no hay un pedido, el agente responde "no tengo esa información en nuestras políticas" sin llamar al modelo. Los márgenes se ajustaron con 122 preguntas divididas en desarrollo y prueba: el híbrido recupera el documento correcto en 67 de 70 y 30 de 32. De un banco aparte de 75 preguntas ajenas al negocio se rechazan 73.

## Pruebas automatizadas

Comando exacto: `python -m pytest tests/` (o `pytest tests/` si pytest ya está instalado). Son 828 tests que corren en unos 20 segundos, sin red ni `.env`, en modo offline. Hay dos opt-in que necesitan Ollama (`TIENDAHOGAR_TEST_OLLAMA=1`).

Lo primero que hay que leer es `tests/test_criticos.py`: los tres casos críticos del enunciado y los límites ($500 no escala y $501 sí, liquidación, pedido inexistente) en pocos tests. El detalle está repartido así:
- Recuperación: `test_rag.py` y `test_recuperador.py`. Cada documento se recupera con su pregunta y las preguntas fuera de alcance no superan el umbral.
- Tool de pedidos: `test_pedidos.py` y `test_pedidos_flexibles.py`. Los cuatro pedidos válidos, los inexistentes o mal formados ("No encontrado", sin inventar) y el número escrito de muchas formas.
- Guardrail: `test_guardrails.py` y `test_semantica.py`. Reembolsos de $501 o más, el de $500 que no escala, formatos de monto (`$1.000`, `2k`, `mil quinientos`), quejas, facturación, temas legales, paráfrasis, faltas de ortografía e inyección.
- Escenarios y ataques: `test_agente.py`, `test_mixtas.py`, `test_fuera_de_alcance.py` y `test_adversarial.py` (75 preguntas ajenas y 72 intentos de sacar al agente de su alcance, ninguno se obedece).
- Conversación: `test_sesion.py` y `test_lugares.py`. Repreguntas, límites de turnos y que el guardrail corre dentro de una sesión.
- Clientes de modelo: `test_llm.py`, contra un servidor local que imita cada API.

Mediciones sobre conjuntos de frases (no son tests; se corren con `python -m tiendahogar.evaluacion` y `python -m tiendahogar.independiente medir`). Con embeddings el guardrail detecta el 98,9 % del riesgo en desarrollo y el 97,6 % en prueba, con 0 falsos positivos, pero esas cifras son optimistas porque el conjunto lo escribí yo. La cifra honesta es la de un lote de 42 frases escrito al final y medido una sola vez antes de tocar nada: 8 de 10 en riesgo con 0 falsos positivos en 29 (5 o 6 de 10 sin embeddings). Sus fallos se corrigieron con reglas generales y están en el [ADR 0010](docs/adr/0010-estrategia-de-evaluacion.md).

## Cómo mapearías esto a producción

- Microsoft Foundry: el agente pasa a ser un agente de Foundry con el modelo desplegado ahí. `consultar_estado_pedido` se registra como tool (function calling) y las reglas de escalamiento quedan como capa previa en código, más Content Safety y Prompt Shields. Las trazas se reemplazan por la telemetría y las evaluaciones de Foundry.
- Databricks y Unity Catalog: los documentos se publican como tablas gobernadas con un índice de Mosaic AI Vector Search. El recuperador se cambia por una consulta híbrida a ese índice, manteniendo la interfaz `buscar` y el umbral por margen.
- Apigee: el agente se expone con autenticación, cuotas y auditoría. La tool de pedidos llama a la API real a través del mismo gateway, con el usuario autenticado para que solo vea sus pedidos, y esa API aporta el valor real de la compra para la regla de los $500.
- Kafka: las derivaciones a un humano se publican como evento (por ejemplo `soporte.escalamientos`) y un consumidor crea el caso. Los eventos de cada conversación salen también hacia observabilidad y evaluación continua.
- Estado de la conversación: hoy la sesión es un objeto en memoria. En producción vive en un almacén por conversación con vencimiento, y el lugar del cliente sale de su dirección de entrega.
- Además: secretos en un gestor, redacción de datos personales antes de registrar (los números de pedido permiten rastrear una conversación) y evaluación en CI con preguntas reales anonimizadas.

## Limitaciones conocidas

- Los clientes de modelo (`OpenAICompatible` y `Anthropic` en `llm.py`) se probaron contra un servidor local que imita cada API y de punta a punta con `qwen2.5:7b` y `embeddinggemma` en Ollama. No los probé contra la API de un proveedor comercial: [completar con el proveedor real que se pruebe antes de entregar].
- Las cifras salen de conjuntos de frases que escribí yo o que se derivaron de las de otra persona, y se ajustaron mirándolos. Un lote ajeno puede dar peores resultados.
- Los guardrails y las frases de ejemplo están en español, el inglés se cubre solo en parte, y la detección de inyección se limita a lo inequívoco: es una defensa básica, no una garantía.
- Hay decisiones propias que los documentos no dan: hasta $500 el agente no deriva ni promete la aprobación, "la capital" es la Ciudad de Buenos Aires, y el monto de una compra es el que declara el cliente porque la tabla de pedidos no tiene precios.
- El diccionario de lugares es una muestra: un lugar que no figura se trata como desconocido y se repregunta.
- La memoria cubre pocos datos y vive en el proceso; sin sesión, cada pregunta se trata sola. La validación de la salida del modelo (palabras sin respaldo) está calibrada a mano con un modelo local y es una red de seguridad, no una garantía.
- El RAG a veces recupera solo uno de dos documentos en preguntas que los mezclan y falla en paráfrasis lejanas. En modo offline, una pregunta fuera de tema que comparte una palabra del dominio recibe el documento completo.
- Varias consultas a la vez: sin modelos, 32 clientes simultáneos dan las mismas respuestas que uno solo, sin errores. No medí varios clientes contra un mismo modelo de lenguaje.
- Los documentos no dicen precios, marcas ni garantía extendida: el agente responde que no tiene esa información.
- Los tests y las mediciones se corrieron en Windows con Python 3.11.

## Tiempo invertido

Aproximadamente 8 horas hasta ahora.
