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
- Los guardrails son reglas en español. No cubren paráfrasis raras, otros idiomas ni ironía. Un monto escrito de forma rara (por ejemplo "quinientos cincuenta") se detecta solo para unos pocos casos. Un reembolso sin monto explícito no escala: el agente informa la política y la regla de los $500, y no promete que haya sido aprobado ni ejecutado.
- Una devolución de un producto de más de $500 mencionada como "devolver una estufa de $900" se escala por prudencia aunque el cliente no use la palabra reembolso. Es una decisión mía, no está en los documentos.
- La tabla de conceptos del RAG y el umbral se ajustaron a mano con pocas preguntas. Con preguntas reales habría que medir y reajustar. En modo offline una pregunta fuera de tema que comparta un concepto con un documento (por ejemplo "cuánto cuesta el envío") recibe el documento de envíos completo, no la respuesta exacta.
- No hay memoria entre mensajes: cada pregunta se trata sola. Si el cliente da el número de pedido en un mensaje y pregunta en otro, el agente no los une.
- Los documentos no dicen precios, marcas, garantía extendida ni qué pasa con un reembolso de más de $500 más allá de la aprobación del supervisor. El agente dice que no tiene esa información.
- La salida del modelo no se valida después de generarla (por ejemplo citas o montos inventados). El prompt limita lo que puede usar y el contexto es corto, pero no hay una segunda verificación.
- Los tests se corrieron en Windows con Python 3.11.

## Tiempo invertido

[Completar: horas aproximadas]

---

## REGISTRO DE DECISIONES (borrador de trabajo: integrar en las secciones de arriba y borrar este bloque antes de entregar)

Las secciones de arriba salieron de una primera versión escrita sin revisar las decisiones. Quedan válidas solo las que figuran como "Decidido" acá, y el resto se reescribe a medida que se decide.

### Decidido

1. Orquestación determinística, sin framework. El código decide el flujo (inyección, guardrail, tool, RAG, redacción) y el LLM solo redacta con lo recuperado. No se usa LangChain ni LangGraph: con 5 documentos, una tool y un flujo lineal agregan capas que esconden lo que se quiere mostrar y suman dependencias. Serían una opción razonable si el corpus y las tools crecen mucho, con flujos con ramas, estado o varios agentes. En producción, el equivalente natural es el SDK de agentes de Microsoft Foundry. Además, dejar el guardrail y la tool fuera de las manos del modelo protege frente a modelos chicos que se equivocan (el modelo local de 3B falló en preguntas que mezclan garantía y devolución).

3. RAG híbrido: embeddings más BM25. Fundamento: la plantilla del enunciado pregunta qué modelo de embeddings se usó y por qué, y con embeddings se recuperan paráfrasis y textos con faltas de ortografía que BM25 no ve. BM25 se mantiene por tres razones: es el respaldo si el proveedor de embeddings falla, permite que los tests y el agente corran sin red ni claves, y combinar ambas señales (fusión por posición) es más robusto que cualquiera sola. Chunking: no se parten los documentos porque cada uno tiene menos de 400 caracteres y una sola política; partirlos separaría frases que se necesitan juntas (la regla de devoluciones y su excepción). Umbral: no es un número absoluto de similitud, porque cada modelo de embeddings tiene su propia escala y el agente debe funcionar igual si ellos usan otro modelo. Un documento se considera relevante si su similitud supera por un margen a la de un conjunto de preguntas fuera de alcance. Si nada lo supera, el agente responde que no tiene esa información y no llama al modelo de lenguaje. El margen se ajusta con un conjunto de preguntas dividido en desarrollo y prueba, con las mismas salvedades que el del guardrail.
4. Consulta de pedidos flexible, en tres capas determinísticas. Fundamento: llamar a la tool solo cuando aparece el texto exacto `ORD-XXXX` es frágil, porque los clientes escriben "pedido 1001", "ord 1001", "orden de compra 1001" o "mi pedido es el 1001". (1) Extracción flexible del número: se aceptan el prefijo `ORD` con cualquier separador o guion y las formas "pedido", "orden", "nro", "n°", "#" y listas, se normaliza a `ORD-XXXX` y se muestra en la respuesta el número que se entendió, para que el cliente corrija si hubo un malentendido. Un número suelto sin contexto de pedido no cuenta, porque puede ser un monto o un plazo. (2) Intención por significado: una categoría "consulta de pedido" en el clasificador semántico reconoce preguntas como "ya salió lo que compré?" aunque no digan "pedido" ni den un número, y en ese caso el agente pide el número. (3) No se busca por nombre de producto: la tabla tiene un pedido por producto, pero un cliente real puede tener varios, y adivinar sería inventar datos, que el enunciado prohíbe. Un número mal formado o inexistente devuelve "No encontrado". Descartado: tolerar la letra O por el cero ("ORD-1O01") porque puede atribuir mal un pedido, y usar un modelo de lenguaje para extraer el número, porque rompe la decisión de que el flujo lo decide el código y no el modelo.

Implementación y medición del RAG (decisión 3): `RecuperadorHibrido` en `rag.py`. Cada documento se compara con la consulta entero y por oración (la similitud de un documento es la mayor de sus partes), porque las consultas son cortas y cada documento mezcla varias reglas. Un documento es relevante si su similitud supera por 0,08 a la de las preguntas fuera de alcance (`data/fuera_de_alcance.json`) o si BM25 lo considera relevante; se ordenan por fusión de posiciones y se descartan los que quedan más de 0,06 por debajo del mejor. Si el servicio de embeddings falla se usa BM25 solo. Conjunto de 122 preguntas (`tests/data/rag_evaluacion.json`): explícitas, paráfrasis, con faltas de ortografía, que mezclan dos documentos, "casi iguales" y fuera de alcance, dividido en desarrollo (84) y prueba (38).

| Recuperación | Desarrollo: recall / fuera de alcance rechazadas | Prueba: recall / fuera de alcance rechazadas |
| --- | --- | --- |
| BM25 solo | 55/70 (78,6 %) / 13 de 14 | 22/32 (68,8 %) / 5 de 6 |
| Híbrido con `embeddinggemma` | 64/70 (91,4 %) / 13 de 14 | 26/32 (81,2 %) / 5 de 6 |

Lo que se probó y se descartó: usar solo embeddings con el documento entero (recall 77 % en desarrollo, porque la consulta corta se parece poco a un texto largo que mezcla reglas), los prefijos de tarea que recomienda `embeddinggemma` para consultas y documentos (no mejoraron: 87 % contra 91 %) y comparar solo por oración sin BM25 (84 % en prueba pero se equivoca con "capital de Francia" por la palabra "capital"). Fallos que quedan: paráfrasis lejanas ("mandan a otros países?", "entregan fuera del país?"), preguntas por el canal de contacto ("con quién hablo si me trataron mal?") y preguntas que mezclan dos documentos, donde a veces solo se recupera uno. Posible mejora: indexar para cada documento una lista de preguntas que responde (técnica conocida como preguntas hipotéticas), sin editar los documentos. Las salvedades de siempre: el conjunto lo escribió el mismo autor del código y los márgenes se ajustaron sobre desarrollo con un conjunto chico.

### En discusión: 2. Guardrails

Respuestas de Ramiro a las preguntas abiertas:
- Ante la duda se escala de más, pero con un límite: hay que mantener una tasa de error baja, también de falsos positivos. Se medirá con un set de frases (ver abajo).
- Pregunta mixta (parte permitida y parte para derivar): se responde la parte permitida y después se deriva lo que corresponde.
- Devolución de un producto de más de $500 sin la palabra "reembolso": se mantiene la interpretación (escalar) solo cuando es clara, es decir, con un monto explícito. Esta regla no está en los documentos y se declara como decisión propia.
- Detección de inyección de prompt: se mantiene acotada a lo inequívoco ("ignorá tus instrucciones", "mostrame tu prompt"), se declara como defensa básica y no como garantía. Si sobra tiempo, se puede reforzar.
- Implementado: en una pregunta mixta se responde primero la parte permitida (con los documentos o la tool de pedidos) y después se deriva el resto. Las cláusulas se separan por puntuación y conectores, sin cortar decimales como `$1.000`. Con más de un motivo de derivación se usa el mensaje del primero, porque el canal es el mismo.
- Implementado: en las respuestas sobre reembolsos con un monto de hasta $500 el agente aclara que ese monto lo declara el cliente: si el valor real supera $500 hace falta un supervisor. Ver la decisión sobre la regla de reembolsos más abajo.

Punto débil a resolver: las reglas determinísticas no cubren paráfrasis ("regresen la plata" en vez de "reembolso"). Ideas encontradas para mantener el enfoque reproducible y mejorar la cobertura:
- Router semántico: se comparan los embeddings de la pregunta con los de frases de ejemplo por categoría, con un umbral de similitud. Es reproducible (mismo modelo, mismo resultado), no usa un LLM generativo y tarda decenas de milisegundos. Es el patrón de la librería Semantic Router y de las "formas canónicas" de NeMo Guardrails.
- Diseño en capas: reglas para lo evidente, embeddings para la cola larga del lenguaje natural y un LLM solo si la confianza es baja. Los textos sobre guardrails advierten que la coincidencia de patrones debe ser una señal entre varias y que se debe medir con casos reales de falsos positivos y negativos.
- Respaldo offline: similitud por n-gramas de caracteres sobre las mismas frases de ejemplo (tolera tildes, typos y variaciones de forma) con librería estándar.
- Un set de paráfrasis y de casos "parecidos pero permitidos" (por ejemplo "necesito la factura para la garantía") sirve para decidir con datos y queda como evidencia en la entrega.

Fuentes consultadas: Semantic Router (https://pub.towardsai.net/semantic-router-the-ai-traffic-controller-4a55f7fe7c35), comparación de guardrails (https://blog.premai.io/production-llm-guardrails-nemo-guardrails-ai-llama-guard-compared), Building Guardrails for Large Language Models (https://arxiv.org/pdf/2402.01822).

Decidido dentro de la 2 (confirmado por Ramiro): guardrail en tres capas, todas reproducibles: (1) reglas para lo evidente, (2) similitud semántica por embeddings contra frases de ejemplo por categoría, con umbral, y (3) respaldo offline por n-gramas de caracteres con librería estándar. El LLM generativo no clasifica. Se arma primero un set de frases (de riesgo, normales y "casi iguales") para medir detección y falsos positivos antes de fijar umbrales. Sin librerías nuevas: los embeddings se piden por HTTP al endpoint `/v1/embeddings` (el mismo que exponen Ollama y OpenAI) y el coseno se calcula en Python.

Modelo local de embeddings candidato: `bge-m3` (1,2 GB, 567 millones de parámetros, más de 100 idiomas) o `embeddinggemma` (622 MB, 300 millones, multilingüe). Se elige con el set de frases, no a ojo.

Modelo local de generación: se descartó `qwen2.5:3b` y queda `qwen2.5:7b`. En 7 preguntas de prueba, el 3B respondió mal la pregunta que mezcla garantía y devolución (45 días con falla) y enredó la de una licuadora de 8 meses, y el 7B respondió bien las 7. A cambio tarda más, unos 11 a 25 segundos por respuesta en CPU contra 5 a 15 segundos. Es una prueba chica, no una medición.

Set de frases (en `tests/data/`): `guardrail_anclas.json` son los ejemplos que usa el router y `guardrail_evaluacion.json` son 205 frases de evaluación que el router no ve (130 de riesgo, 70 permitidas, 5 de inyección). Tipos: explícitas, paráfrasis, variantes (inglés, mayúsculas, texto largo), casi iguales, mixtas, límite de $500, ambiguas, normales, montos (formatos de número, números en palabras y moneda) y ortografía (faltas en la palabra de reembolso, queja, cobro o demanda). Línea base de las reglas actuales: detectan 89 de 130 frases de riesgo (68 %) con 1 falso positivo en 70 permitidas. Fallan sobre todo en paráfrasis de queja de trato y de facturación, en inglés, en 4 de 27 formatos de monto y en 14 de 24 frases con faltas de ortografía. Las reglas de esa medición se escribieron antes que el set y es probable que sobreestimen la cobertura real.

Medición de las capas sobre las 205 frases (detección de riesgo sobre 130 frases y falsos positivos sobre 70 permitidas; la capa de embeddings compara con las anclas y decide por margen contra la clase "permitida"):
- Reglas solas: 89/130 (68 %), 1 falso positivo.
- Reglas más n-gramas de caracteres (respaldo offline, solo librería estándar): 104/130 (80 %), 2 falsos positivos.
- Reglas más `bge-m3`: 124/130 (95 %), 3 falsos positivos con un margen de 0,06.
- Reglas más `embeddinggemma`: 125/130 (96 %), 1 falso positivo con un margen de 0,06 a 0,08, y el resultado es estable en ese rango.
- Los umbrales y márgenes se eligieron sobre el mismo set con el que se mide, así que las cifras son optimistas. Hay que separar un set de desarrollo y otro de prueba antes de reportarlas.
- Decidir por margen contra "permitida", y no por un umbral absoluto de similitud, hace al método más portable entre modelos de embeddings, que tienen escalas de similitud distintas.
- Los 5 fallos restantes de `embeddinggemma`: 4 son formatos de monto que el parser no entiende ("quinientos un", "$ 1 200", "$2k", "1.5k") y 1 es una pregunta mixta donde la parte permitida diluye a la queja (se resuelve evaluando cada oración por separado).

Implementado (modelo de embeddings elegido: `embeddinggemma`, 622 MB; se descartó `bge-m3`): parser de montos (`montos.py`), clasificador por embeddings con respaldo por n-gramas (`semantica.py`), evaluación de cada oración por separado y evaluación del set (`python -m tiendahogar.evaluacion`). La intención de reembolso también tolera faltas de ortografía en las reglas (coincidencia aproximada). El set de 200 frases (sin las 5 de inyección) se dividió en desarrollo (135, para ajustar el margen) y prueba (65, sin tocar al ajustar). Margen elegido sobre desarrollo: 0,07 (estable de 0,06 a 0,08).

| Configuración | Desarrollo: riesgo / falsos positivos | Prueba: riesgo / falsos positivos |
| --- | --- | --- |
| Solo reglas | 70/88 (79,5 %) / 0 de 47 | 33/42 (78,6 %) / 0 de 23 |
| Reglas + n-gramas (offline) | 74/88 (84,1 %) / 0 de 47 | 40/42 (95,2 %) / 0 de 23 |
| Reglas + embeddinggemma | 87/88 (98,9 %) / 0 de 47 | 41/42 (97,6 %) / 1 de 23 |

Esta tabla es posterior a sumar la categoría "consulta de pedido" al clasificador. Al sumarla, los falsos positivos con embeddings subieron a 3 de 47 en desarrollo y 2 de 23 en prueba, porque las frases sobre el estado de un pedido ("Estado de ORD-9999") dejaron de estar entre las anclas permitidas y se parecían a una disputa de facturación. Se corrigió haciendo que, para decidir riesgo, "lo permitido" incluya también las consultas de pedido: preguntar por un pedido nunca es un reclamo. Fallos que quedan con embeddings: "boy a tomar acciones lejales" y "los boy a denunsiar" (faltas de ortografía en frases legales) y, como falso positivo, "Quiero un reembolso de 2 productos, uno de $200 y otro de $150" (la marca como disputa de facturación). Salvedad importante: el set y las anclas los escribió la misma persona en la misma sesión, así que la división en desarrollo y prueba no equivale a una prueba independiente y las cifras son optimistas. La medición real vendrá de frases escritas por otra persona.

Decisiones tomadas con Ramiro sobre el set:
- Una pregunta sobre el canal ("con quién hablo si tengo un tema legal?") se responde con el correo del Doc 5 y se ofrece derivar. No se trata como un escalamiento ciego.
- La robustez ante errores de ortografía y ante formatos de monto es un requisito, no un extra: el set incluye casos de ambos.
- El monto del reembolso: el enunciado no da precios de los productos, así que el agente no puede saber el valor real de una compra y se apoya en el monto que declara el cliente. Inventar un catálogo de precios sería agregar datos que el enunciado no da. En las respuestas sobre reembolsos con un monto de hasta $500 se aclara que si el valor real de la compra lo supera hace falta un supervisor. En producción, el monto vendría de la API de pedidos.

### Decisión: qué hace el agente con un reembolso de hasta $500 (confirmada por Ramiro)

El Doc 4 dice: "Reembolsos mayores a $500 requieren aprobación de un supervisor humano — el agente no debe aprobarlos automáticamente". La prohibición explícita es solo para los de más de $500, pero el documento no dice quién aprueba los de $500 o menos ni que el agente deba aprobarlos. El enunciado agrega que el guardrail debe derivar los casos que "los documentos indican que no debe manejar" (reembolsos mayores a $500, entre otros), lo que implica que los de hasta $500 sí los maneja, es decir, los responde sin derivar. Tres hechos del enunciado impiden que el agente apruebe o ejecute reembolsos: la única tool es de solo lectura (`consultar_estado_pedido`), la tabla de pedidos no trae precios (el monto lo declara el cliente y no se puede verificar) y la política pone condiciones que el agente no puede comprobar (30 días, producto sin usar y en su empaque, o defecto cubierto por la garantía). Afirmar "tu reembolso está aprobado" sería inventar una acción y permitiría obtener una "aprobación" declarando un monto menor. Por eso, hasta $500 el agente no deriva: informa la política (se procesa en 5 a 10 días hábiles después de recibir el producto devuelto, al mismo método de pago original), aclara que con ese monto no hace falta la aprobación de un supervisor y avisa que, si el valor real de la compra lo supera, sí la requiere. No dice que el reembolso esté aprobado ni que no pueda aprobarlo. En producción, una API de aprobación detrás de Apigee tomaría el monto de la API de pedidos y aprobaría automáticamente hasta $500, y un evento a Kafka derivaría al supervisor lo que supere ese tope.

### Principio para elegir el modelo de lenguaje (decisión de Ramiro)

Cuanto mejor es el modelo, menos defensas necesita el código. Para que el diseño sea realista, no se apunta a un modelo de última generación (no es lo que se usaría en un soporte de este tipo por costo) ni a uno viejo (obligaría a sobreajustar el código). Se apunta a la clase de modelos más usada por su relación costo y calidad: los modelos chicos de los proveedores comerciales (la gama "mini", "flash" o "haiku") y, en local, un modelo abierto de 7 a 8 mil millones de parámetros. En las pruebas locales se usó `qwen2.5:7b` como referencia, por ser una clase igual o inferior a los modelos chicos comerciales: si el agente funciona bien con él, debería funcionar con un modelo de esa gama. El 3B se descartó porque falló en las preguntas que mezclan garantía y devolución. La lentitud medida (unos 20 segundos por respuesta) se debe al hardware de la máquina de desarrollo (CPU, sin GPU) y no al diseño.

### Limitaciones declaradas por decisión

- Solo español: el enunciado, los documentos y las pruebas están en español, y el inglés no aparece en ningún lado. Una pregunta en otro idioma se responde en español o no se entiende.
- Cuando una pregunta queda fuera del alcance de los documentos (precios, marcas, garantía extendida), el agente responde que no tiene esa información.
- El agente no confirma ni promete que un reembolso o una devolución fue aprobado o ejecutado: informa la política (plazos, método de pago y condiciones) y deriva lo que corresponde.

### Performance: qué depende del modelo y qué depende de la herramienta

Criterio acordado con Ramiro: separar la latencia que depende de los modelos (el de lenguaje que redacta y el de embeddings, que cambian con el modelo y el hardware) de la que depende de la herramienta (guardrail, recuperación, tool de pedidos, validación), donde sí hay que optimizar. Cada respuesta del agente trae `tiempos` con tres baldes (modelo de lenguaje, modelo de embeddings y código propio) y el tiempo de cada etapa, y quedan en la traza. `python -m tiendahogar.rendimiento` mide 16 preguntas representativas (consultas de política, pedidos, derivaciones, mixtas y fuera de alcance) en tres modos. Hardware de las pruebas: una PC con Windows, 15,8 GB de RAM y sin GPU, con Ollama.

Estado inicial, herramienta con embeddings y sin modelo de lenguaje: 2129 ms de mediana por pregunta nueva, de los cuales 2102 ms eran el servicio de embeddings y 33 ms el código propio; el arranque en frío tardaba 12,5 s (3 llamadas).

Lo que se encontró y se hizo:
- El tiempo constante de 2,1 s por llamada no era del modelo: Ollama reportaba 35 ms de cómputo para un texto. Era la resolución de `localhost` en Windows, que prueba primero IPv6 mientras el servidor escucha en IPv4. Con `127.0.0.1` la llamada tarda 44 ms (47 veces menos). El cliente HTTP ahora reemplaza `localhost` por `127.0.0.1` y vuelve a la dirección original si el servidor no responde ahí.
- Código propio: de 33 ms a 5 ms de mediana. Los vectores se guardan normalizados y la similitud es un producto punto en vez de recalcular las normas cada vez, y los puntajes de cada oración se recuerdan para que el guardrail y la intención de pedido no los calculen dos veces.
- Llamadas evitadas: si las reglas ya derivan una pregunta de una sola cláusula (por ejemplo "Quiero un reembolso de $900") no se consulta el modelo de embeddings, y una pregunta con número de pedido no evalúa la intención. Una pregunta normal hace una sola llamada de embeddings: el guardrail y el recuperador comparten el cliente y el texto se pide una vez.
- Arranque en frío: los embeddings de los textos fijos (documentos, preguntas fuera de alcance y frases de ejemplo del guardrail) se piden en una sola llamada y se guardan en disco (`.cache/`, 1,5 MB, ignorado por git; nunca se guardan preguntas de clientes). El primer arranque bajó de 12,5 s a 3,9 s y los siguientes tardan 122 ms.

Resultados actuales (mediana por pregunta nueva, en milisegundos):

| Modo | Total | Modelo de lenguaje | Modelo de embeddings | Código propio |
| --- | --- | --- | --- | --- |
| Sin ningún modelo (reglas, n-gramas y BM25) | 2,5 | 0 | 0 | 2,5 |
| Herramienta con embeddings, sin modelo de lenguaje | 70 | 0 | 65 | 5 |
| Completo, con `qwen2.5:7b` local en CPU | 6973 | 6863 | 81 | 9,6 |

Con el modelo de lenguaje, el modelo explica el 98 % del tiempo (la mediana de la herramienta completa, sin contar al modelo de lenguaje, es de unos 90 ms). Los percentiles altos del modelo de lenguaje son de carga y de generación: la primera pregunta tardó 47 s porque Ollama carga el modelo en memoria (se puede evitar manteniéndolo cargado con `OLLAMA_KEEP_ALIVE`) y las respuestas largas llegan a 15 a 45 s en CPU. Esa parte no depende de nuestro código, salvo el largo de la respuesta que se le pide al modelo.

Largo de la respuesta (experimento con `qwen2.5:7b` local, 10 preguntas con datos esperados fijos, por ejemplo "6 meses" o "5-10"): se compararon cuatro versiones del pedido al modelo.

| Versión | Generación, mediana | Palabras medias | Calidad |
| --- | --- | --- | --- |
| A, sin límite | 19,7 s | 20,2 | 8 de 10 |
| B, "máximo 2 oraciones" | 18,0 s | 18,3 | 8 de 10 |
| C, "una o dos oraciones, sin repetir la pregunta ni agregar consejos" | 18,2 s | 16,4 | 8 de 10 |
| D, C con tope de 200 tokens | 17,8 s | 16,4 | 8 de 10 |

Medido aparte contra Ollama: el modelo genera unos 3,1 tokens por segundo en esa CPU, es decir 0,32 s por token, y leer un prompt de unos 400 tokens cuesta entre 7 y 14 s si cambia y casi nada si el comienzo se repite (Ollama reutiliza el prefijo). Conclusiones: (1) limitar el largo ayuda poco en la mediana, porque casi todas las respuestas ya eran cortas, pero sí en la cola: la pregunta de 45 días generaba 93 tokens (31 s) y con la indicación de brevedad baja a la mitad; (2) el tope de tokens no aporta nada y puede cortar respuestas, así que no se usa; (3) se adoptó la versión C dentro del pedido al modelo; (4) el tiempo grande de la generación depende de los tokens que el modelo escribe y de los que lee, y en una GPU o con un modelo comercial es una fracción de esto.

La prueba encontró un fallo de calidad independiente del largo: el modelo omitía a veces la aclaración de la regla de los $500 y el aviso de pedir el número de pedido, que le llegaban como notas en el pedido. Un modelo chico puede ignorar lo que no se le pide con fuerza, y esas aclaraciones son obligatorias. Ahora el modelo no las recibe: las agrega el código al final de la respuesta, con o sin modelo de lenguaje. Con ese cambio la calidad subió de 8 a 10 de 10 en las mismas preguntas.

Dos opciones que se evaluaron para acelerar o completar las respuestas, con la decisión de Ramiro:
- Responder con la oración exacta del documento, sin modelo de lenguaje, cuando la pregunta corresponde claramente a una sola oración. Descartada: sería casi instantáneo y no puede inventar, pero le quita naturalidad a la herramienta.
- Completar la cobertura con los documentos que el modelo no citó. Adoptada. Una pregunta que mezcla políticas (por ejemplo "mi lavadora tiene 45 días y falla, la puedo devolver?", que toca devoluciones y garantía) a veces recibe del modelo una respuesta que cubre solo una. Ahora, después de validar la respuesta, el código revisa los dos documentos mejor rankeados y agrega, con su título y su cita, el texto de los que la respuesta no cubre. Un documento cuenta como cubierto si la respuesta lo cita o si ya usa alguna de sus cifras (por ejemplo "12 meses"), para no repetir lo que el modelo ya dijo. Solo se completan los dos mejores documentos porque el tercero suele ser un extra marginal. Con el modelo apagado (modo offline) no hace falta: la respuesta ya cita todos los documentos recuperados.

Costo de completar la cobertura, medido en el peor caso (se supone que el modelo cita solo el primer documento) sobre las 102 preguntas del conjunto de RAG que tienen documentos esperados: se agrega texto en 9 de las 102; en 7 era útil (6 de las 10 preguntas que mezclan dos documentos quedan cubiertas) y en 2 era de más (2 %, ambas preguntas sobre reembolsos que arrastraron un documento vecino). Con el modelo real, las 10 preguntas de prueba mantienen 10 de 10 de calidad y solo una recibió texto agregado, el que hacía falta.

Pendiente: medir el comportamiento con varias consultas a la vez.

### Prueba del CLI desde un clon limpio, sin `.env`

Se clonó el repositorio en una carpeta nueva, sin `.env` ni entorno virtual, con el Python del sistema (solo librería estándar) y los comandos del README. Sin configuración, el agente corre en modo offline (reglas, n-gramas de caracteres y BM25) y responde en unos 0,3 s por pregunta. Se probaron 13 preguntas representativas (garantía, devoluciones, mixtas, pedidos con distintos formatos, derivaciones, fuera de alcance e intento de inyección), el chat interactivo y los casos límite: todo respondió sin errores. Hallazgos y correcciones:
- Con un servidor de modelos caído, una sola pregunta tardaba 9 s (solo modelo de lenguaje) y hasta 37 s (con embeddings), porque cada llamada del agente esperaba sus propios reintentos. Ahora una conexión rechazada falla enseguida, sin reintentos, y un servicio que acaba de fallar no se vuelve a intentar durante 30 segundos. Tiempos actuales: 2,3 s la primera vez (lo que tarda Windows en rechazar la conexión) y sin espera en las llamadas siguientes. La detección de la conexión rechazada ya no depende del idioma del sistema, que antes fallaba en Windows en español porque comparaba el texto del mensaje.
- Una consulta vacía respondía "no tengo esa información" y ahora pide la consulta.
- Una consulta de 22.500 caracteres tardaba 0,73 s y una línea de 200.000 caracteres tardaba 4 s; ahora se recortan a 2000 caracteres (queda un evento en la traza) y tardan 0,3 s.
- La traza guardaba el texto de la cláusula del cliente en las preguntas mixtas. Ahora guarda solo la cantidad.
- Probado y sin problemas: caracteres nulos y de control, emoji, texto mal codificado (se responde que no hay información), cierre de la entrada estándar, proveedor desconocido (mensaje claro y código de salida 2), modelo o clave faltante (mensaje claro y código de salida 2).

Qué guardan las trazas (`trazas/trazas.jsonl`, ignorada por git): largo de la consulta, categorías del guardrail, documentos recuperados con sus puntajes, números de pedido consultados, si el modelo de lenguaje respondió o se descartó su respuesta y los tiempos. No guardan el texto de la consulta ni de la respuesta. Los números de pedido son identificadores que permiten rastrear una conversación: en producción habría que decidir su retención junto con el resto de los datos de la conversación.

### Lista de mejoras si queda tiempo

- Memoria entre mensajes (por ejemplo, unir el número de pedido dado antes con una pregunta posterior).
- Ingeniería adicional contra inyección de prompt, más allá de lo inequívoco.
- Respuestas más útiles a preguntas fuera de alcance, por ejemplo ofrecer derivar a una persona.
- Soporte de otros idiomas.
- Revisar qué hace el CLI sin Ollama ni clave, y qué datos guardan las trazas.

### Pendientes (se tratan en orden)

3. RAG: BM25 sin embeddings y umbral calibrado a mano. Revisar si conviene embeddings (ver el router semántico) y cómo se justifica el umbral.
4. Cuándo se llama a la tool de pedidos (hoy, siempre que aparece ORD-XXXX).
5. Comportamiento del agente en preguntas mixtas y fuera de alcance.
6. Validación de la salida del LLM (hoy: cifras o correos inventados y respuestas muy cortas).
7. Modo offline sin LLM como respaldo.
8. Clientes de LLM con urllib, sin SDK (y modelo local elegido: qwen2.5 3B o 7B según pruebas).
