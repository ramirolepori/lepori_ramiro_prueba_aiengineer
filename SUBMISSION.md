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
  8. traza JSONL y tiempos por etapa
```

El flujo lo decide el código y el modelo de lenguaje solo redacta con lo recuperado. Lo que el enunciado trata como regla (derivar reembolsos mayores a $500, quejas de trato, disputas de facturación y temas legales, no inventar datos, no aprobar reembolsos) corre en código antes o después del modelo. Así el comportamiento crítico es el mismo con cualquier modelo, también uno chico y local, y se prueba sin red. Sin modelo configurado el agente funciona completo en modo offline (reglas, n-gramas de caracteres y BM25). Con una sesión opcional recuerda qué dato le pidió al cliente (el lugar, el monto, el número de pedido o hace cuánto compró) y lo repregunta en vez de volcar un documento entero.

Trade-offs por el límite de tiempo y los datos que dan los documentos:
- Sin framework de agentes ni bucle de tool calling decidido por el modelo. Con 5 documentos, una tool y un flujo lineal, LangChain o LangGraph agregarían capas y dependencias, y un modelo chico se equivoca justo en los casos críticos. Serían razonables si el corpus y las tools crecen mucho. Detalle en el [ADR 0002](docs/adr/0002-orquestacion-deterministica-sin-framework.md).
- El guardrail combina reglas (lo evidente), similitud por embeddings contra frases de ejemplo (paráfrasis y faltas de ortografía) y n-gramas de caracteres como respaldo sin red. Es reproducible: el modelo generativo no clasifica. Las frases de ejemplo están en español, así que otros idiomas se cubren solo en parte. [ADR 0003](docs/adr/0003-guardrail-en-tres-capas.md).
- Los documentos dejan huecos y los resolví con decisiones propias, declaradas: hasta $500 el agente informa la política y no deriva, sin prometer que el reembolso esté aprobado ([ADR 0006](docs/adr/0006-reembolsos-hasta-500.md)); "la capital" del documento de envíos la tomo como la Ciudad de Buenos Aires y el plazo lo decide el código según el lugar ([ADR 0007](docs/adr/0007-envios-segun-el-lugar.md)).
- La consulta de pedidos es flexible (varias formas de escribir el número, sin buscar por nombre de producto y sin corregir en silencio un identificador raro). [ADR 0005](docs/adr/0005-consulta-de-pedidos-en-tres-capas.md).
- Después de generar, el código valida la salida del modelo (cifras o correos inventados), completa la cobertura de las políticas y agrega las aclaraciones obligatorias. [ADR 0010](docs/adr/0010-el-modelo-solo-redacta.md).

Lo que no tiene que ver con la tienda no llega al modelo: sin un documento relevante el agente responde que no tiene esa información, y las órdenes de cambiar sus reglas se bloquean ([ADR 0013](docs/adr/0013-robustez-ante-intentos-de-sacarlo-de-alcance.md)).

Todas las decisiones, con sus alternativas descartadas y su evidencia, están en [docs/adr](docs/adr/README.md). La descripción por módulos y cómo extender el agente está en [docs/arquitectura.md](docs/arquitectura.md).

## Decisiones técnicas de RAG

- Chunking: no. Cada documento tiene menos de 400 caracteres y es una sola política, y partirlo separaría frases que se necesitan juntas (por ejemplo la regla de devoluciones y su excepción). Cada documento es un fragmento. Para comparar con una consulta corta, el recuperador mide la similitud del documento entero y de cada una de sus oraciones, y vale la mayor. `rag.dividir` ya parte por párrafos con solape y es lo que usaría si el corpus creciera a miles de documentos: fragmentos de unos 600 caracteres alineados a títulos y párrafos, con el documento y la sección como metadato, un índice vectorial con recuperación híbrida y reordenamiento de los mejores resultados.
- Embeddings: `embeddinggemma` (622 MB, multilingüe, corre local en Ollama), pedido por HTTP al endpoint `/v1/embeddings`, que también exponen OpenAI y otros proveedores. Lo elegí porque entiende paráfrasis y faltas de ortografía que BM25 no ve, y contra `bge-m3` (1,2 GB) dio mejores resultados con menos peso. BM25 se mantiene junto a los embeddings por tres razones: es el respaldo si el proveedor falla, permite que los tests y el agente corran sin red ni claves, y combinar ambas señales con fusión por posición es más robusto que cualquiera sola. Detalle en el [ADR 0004](docs/adr/0004-rag-hibrido-y-umbral-por-margen.md).
- Threshold de recuperación: no usé un número absoluto de similitud, porque cada modelo de embeddings tiene su propia escala y el agente tiene que funcionar igual si se usa otro. Un documento se considera relevante si su similitud con la consulta supera por 0,08 a la mayor similitud con las preguntas fuera de alcance de `data/fuera_de_alcance.json`, o si BM25 lo considera relevante. Se ordenan por fusión de posiciones, se descartan los que quedan más de 0,06 por debajo del mejor y se usan hasta 3. Si ningún documento supera el umbral y no hay un pedido, el agente responde "no tengo esa información en nuestras políticas" y no llama al modelo. Si la consulta tiene varias cláusulas, se recupera para la consulta entera y para cada cláusula. Los márgenes se ajustaron con un conjunto de 122 preguntas dividido en desarrollo y prueba (84 y 38): el híbrido recupera el documento correcto en 67 de 70 preguntas de desarrollo y 30 de 32 de prueba (BM25 solo: 68 de 70 y 29 de 32) y rechaza 13 de 14 y 6 de 6 de las preguntas fuera de alcance. Aparte, de un banco de 75 preguntas ajenas al negocio (trivia, cálculos, recetas, código...) se rechazan 73 sin citar ningún documento.

## Pruebas automatizadas

Comando exacto: `python -m pytest tests/` (equivale a `pytest tests/` si pytest ya está instalado). Son 782 tests que corren en unos 20 segundos, sin red ni `.env`: usan el modo offline. Hay dos tests opt-in que necesitan Ollama (`TIENDAHOGAR_TEST_OLLAMA=1 pytest tests/test_semantica.py`).

Los tres casos críticos que pide el enunciado:
- Recuperación: `test_rag.py` y `test_recuperador.py` verifican que una pregunta de garantía trae el documento de garantía, que cada documento se recupera con su pregunta, que una pregunta de garantía con devolución trae ambos y que las preguntas fuera de alcance no superan el umbral.
- Tool de pedidos: `test_pedidos.py` y `test_pedidos_flexibles.py` cubren los cuatro pedidos válidos, ids inexistentes o mal formados que devuelven "No encontrado" sin inventar producto ni fecha, y la extracción del número en muchas formas (`ORD-1001`, `pedido 1001`, `compra nro 1003`, `n°2000`) y de identificadores raros (`DRO-1002`).
- Guardrail: `test_guardrails.py` y `test_semantica.py` cubren reembolsos de $501 o más que escalan, el de exactamente $500 que no, "600 días" que no se toma como dinero, quejas de trato, disputas de facturación, temas legales, varias categorías a la vez, formatos de monto (`$1.000`, `2k`, `2 lucas`, `mil quinientos`), lenguaje coloquial, paráfrasis, faltas de ortografía e inyección de prompt.

Además:
- `test_agente.py` y `test_mixtas.py`: escenarios de punta a punta (garantía, producto en liquidación, garantía con devolución, pedido existente, pedido inexistente, pedido sin número, fuera de alcance, reembolso de $500 y de $501, preguntas que mezclan algo para derivar con algo permitido), que el modelo no se llama cuando salta un guardrail, que el prompt solo lleva el contexto recuperado, el respaldo offline si el modelo falla y las trazas.
- `test_fuera_de_alcance.py` y `test_adversarial.py`: 75 preguntas ajenas al negocio y 72 intentos conocidos de sacar al agente de su alcance (anular instrucciones, personajes, extraer el prompt, ofuscación, fragmentar la orden, cambios de tema con autoridad, tareas con texto ajeno, contenido sensible, ruido), más preguntas mixtas y pedidos de promesas. Ninguno se obedece ni se responde con un documento.
- `test_lote3.py`: los casos que mostró el lote 3 (quejas de trato en otras palabras, identificadores raros dentro de una frase, agradecimientos, factura o comprobante que no se entregó con la pregunta de reclamo, productos hechos a pedido, indicaciones internas de los documentos).
- `test_lugares.py`: el plazo de envío según el lugar (Córdoba capital, la capital del país, Buenos Aires ambiguo, exterior, lugar desconocido) y que el modelo no decide el plazo.
- `test_sesion.py`: conversaciones de varios turnos con repreguntas (lugar, monto, número de pedido y antigüedad de la compra), límites de repreguntas y de turnos, sesiones que no se mezclan, y que el guardrail y la inyección corren dentro de una sesión.
- `test_llm.py`: los clientes OpenAI-compatible y Anthropic contra un servidor local (formato del pedido, clave, reintento con `max_completion_tokens`, errores, y el agente de punta a punta con un proveedor).
- `test_montos.py`, `test_rendimiento.py` y `test_independiente.py`: el parser de montos, la medición de latencia por etapa y las herramientas de evaluación.

Mediciones sobre conjuntos de frases (no son tests, se corren con `python -m tiendahogar.evaluacion`, `evaluacion pedidos`, `evaluacion rag` y `python -m tiendahogar.independiente medir`). El guardrail con embeddings detecta el 98,9 % del riesgo en desarrollo (87 de 88) y el 97,6 % en prueba (41 de 42), con 0 falsos positivos en ambos. Esas cifras son optimistas: el conjunto lo escribí yo. En frases escritas por otra persona y en lotes con jerga, los primeros resultados fueron 8 de 10 y 42 de 44, y las correcciones generales llevaron los lotes a 10 de 10 y 44 de 44, que ya no son una medición limpia. Un tercer lote de 42 frases, escrito al final y medido una sola vez antes de tocar nada, dio con embeddings 8 de 10 en riesgo con 0 falsos positivos en 29, 5 de 5 en números de pedido, 15 de 15 en documentos y 8 de 8 en preguntas ajenas rechazadas; sin embeddings el riesgo fue 5 y 6 de 10. Esa es la cifra más honesta del proyecto. Sus fallos (un identificador raro, quejas dichas de otra forma, agradecimientos, un lugar fuera del diccionario) se corrigieron con reglas generales y están en el [ADR 0011](docs/adr/0011-estrategia-de-evaluacion.md). Las cifras y su salvedad están en el [ADR 0003](docs/adr/0003-guardrail-en-tres-capas.md) y el [ADR 0011](docs/adr/0011-estrategia-de-evaluacion.md).

## Cómo mapearías esto a producción

- Microsoft Foundry: el agente pasa a ser un agente de Foundry con el modelo desplegado ahí. `consultar_estado_pedido` se registra como tool (function calling) y las reglas de escalamiento se mantienen como una capa previa en código, más Content Safety y Prompt Shields para inyección. Las trazas JSONL se reemplazan por la telemetría y las evaluaciones de Foundry, y los conjuntos de frases pasan a ser evaluaciones continuas.
- Databricks y Unity Catalog: los documentos se publican como tablas gobernadas en Unity Catalog, con un índice de Mosaic AI Vector Search (o el que defina el equipo) sincronizado con la tabla. El recuperador actual se cambia por una consulta híbrida a ese índice, manteniendo la interfaz `buscar`, el umbral por margen contra preguntas fuera de alcance y el reordenamiento. Los embeddings los da el modelo que se despliegue en el workspace, y el control de acceso lo da Unity Catalog.
- Apigee: el agente se expone detrás de Apigee con autenticación, cuotas, límite de uso y registro de auditoría. La tool de pedidos deja de ser una tabla mock y llama a la API real de pedidos a través del mismo gateway, con el usuario autenticado para que solo vea sus pedidos. Esa misma API aporta el valor real de la compra, y con él el agente deja de depender del monto que declara el cliente para la regla de los $500.
- Kafka: las derivaciones a un humano se publican como evento (por ejemplo un tema `soporte.escalamientos`) en vez de depender de que el cliente escriba un correo, y un consumidor crea el caso en la herramienta de soporte. Los eventos de cada conversación (traza, costo, resultado) también salen por Kafka hacia observabilidad y evaluación continua.
- Estado de la conversación: hoy la sesión es un objeto en memoria que maneja quien llama. En producción vive en un almacén por conversación (por ejemplo el almacén de hilos de la plataforma de agentes) con vencimiento, y el lugar del cliente sale de su dirección de entrega y no del texto de la consulta.
- Además: secretos en un gestor y no en `.env`, redacción de datos personales antes de registrar (los números de pedido permiten rastrear una conversación y habría que definir su retención) y un conjunto de evaluación en CI con preguntas reales anonimizadas.

## Limitaciones conocidas

- Los clientes de modelo (`OpenAICompatible` y `Anthropic` en `llm.py`) se probaron contra un servidor HTTP local que imita la forma de cada API (`tests/test_llm.py`), incluido el rechazo de `max_tokens` que hacen algunos modelos de OpenAI, y de punta a punta con `qwen2.5:7b` y `embeddinggemma` en Ollama. No los probé contra la API de un proveedor comercial: [completar con el proveedor real que se pruebe antes de entregar].
- Las cifras de medición salen de conjuntos de frases que escribí yo o que se derivaron de las de otra persona, y se ajustaron mirándolos. Un lote nuevo y ajeno puede dar peores resultados. Los márgenes y la tabla de conceptos se calibraron con pocas preguntas y habría que reajustarlos con preguntas reales.
- Los guardrails y las frases de ejemplo están en español. El inglés se cubre solo en parte, y no cubren ironía ni paráfrasis muy lejanas. La detección de inyección de prompt se limita a lo inequívoco ("ignorá tus instrucciones"): es una defensa básica, no una garantía.
- Hay decisiones propias que los documentos no dan, y las tomé yo: una devolución de más de $500 con el monto explícito pero sin la palabra reembolso se escala por prudencia; hasta $500 el agente no deriva y no promete la aprobación; "la capital" es la Ciudad de Buenos Aires. El monto de una compra es el que declara el cliente, porque no hay precios en la tabla de pedidos.
- El diccionario de lugares es una muestra, no un catálogo de localidades: un lugar que no figura se trata como desconocido y se repregunta.
- La memoria se limita a lugar, monto, número de pedido y antigüedad de la compra, y vive en el proceso. Sin una sesión, cada pregunta se trata sola. La heurística que decide cuándo preguntar la antigüedad es conservadora: ante la duda no pregunta y responde con la política.
- El RAG a veces recupera solo uno de dos documentos en preguntas que los mezclan, y falla en paráfrasis lejanas ("mandan a otros países?"). En modo offline, una pregunta fuera de tema que comparte una palabra del dominio recibe el documento completo y no la respuesta exacta.
- Varias consultas a la vez sobre un mismo agente: sin modelos, 32 clientes simultáneos dan respuestas idénticas a las de uno solo, sin errores y a unas 1.100 respuestas por segundo (`python -m tiendahogar.rendimiento --offline --concurrente 32`). Con embeddings y preguntas nuevas, lo que limita es el servicio de embeddings y no el código (la latencia crece en cola). No medí varios clientes contra un mismo modelo de lenguaje.
- Los documentos no dicen precios, marcas, garantía extendida ni qué pasa con un reembolso mayor a $500 más allá de la aprobación del supervisor: el agente responde que no tiene esa información.
- Los tests y las mediciones se corrieron en Windows con Python 3.11.

## Tiempo invertido

Aproximadamente 8 horas hasta ahora.
