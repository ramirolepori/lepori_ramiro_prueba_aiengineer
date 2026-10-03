# ADR 0004: RAG híbrido (embeddings y BM25) y umbral por margen

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

La plantilla del enunciado pregunta por el chunking, el modelo de embeddings y el umbral de recuperación, y qué pasa si ningún documento lo supera. Los 5 documentos miden menos de 400 caracteres cada uno y son una sola política. BM25 recupera por palabras y es explicable, pero no ve paráfrasis ni faltas de ortografía ("regresen la plata", "garatnia").

## Decisión

- Chunking: no. Cada documento es un fragmento, porque partirlo separaría frases que se necesitan juntas (la regla de devoluciones y su excepción). `rag.dividir` queda para cuando el corpus crezca: fragmentos de unos 600 caracteres alineados a títulos y párrafos, con el documento y la sección como metadato.
- Recuperador híbrido (`RecuperadorHibrido` en `rag.py`): embeddings con `embeddinggemma` más BM25, fusionados por posición (reciprocal rank fusion). Cada documento se compara con la consulta entero y por oración, y vale la mayor de sus similitudes. Si la consulta tiene varias cláusulas ("cuánto tarda el envío y cuánto de garantía tiene"), se recupera para la consulta entera y para cada cláusula y se juntan los resultados, porque un tema fuerte tapaba al otro.
- Umbral: no es un número absoluto de similitud, porque cada modelo de embeddings tiene su escala y el agente tiene que funcionar igual si el evaluador usa otro. Un documento es relevante si su similitud supera por 0,08 a la mayor similitud con las preguntas fuera de alcance de `data/fuera_de_alcance.json`, o si BM25 lo considera relevante. Se ordenan por fusión y se descartan los que quedan más de 0,06 por debajo del mejor (hasta 3).
- Si ningún documento supera el umbral y no hay pedido, el agente responde que no tiene esa información y no llama al modelo.
- BM25 se mantiene como respaldo: si el servicio de embeddings falla, el agente sigue con BM25 solo, y los tests corren sin red. Para BM25 hay una tabla corta de conceptos (devolver y devolución, enviar y envío, reintegro y reembolso, quemó y garantía...), normalización de tildes y plurales y corrección de faltas leves en las palabras del dominio ("reemoblso"). Una coincidencia con una sola palabra que no es un concepto del dominio ("capital" en "capital de Francia") no cuenta.
- Con miles de documentos: fragmentación con solape, un índice vectorial (ver la sección de producción de `SUBMISSION.md`), reordenamiento de los mejores resultados y un umbral recalibrado con preguntas reales.

## Alternativas descartadas

- Solo BM25: es lo más simple, pero no recupera paráfrasis ni faltas. Queda como respaldo.
- Solo embeddings con el documento entero: 77 % de recall en desarrollo, porque una consulta corta se parece poco a un texto largo que mezcla reglas.
- Solo por oración sin BM25: 84 % en prueba, pero se equivoca con "capital de Francia" por la palabra "capital".
- Prefijos de tarea de `embeddinggemma` para consultas y documentos: no mejoraron (87 % contra 91 %).
- Preguntas hipotéticas por documento (indexar qué preguntas responde cada uno): posible mejora, no implementada.

## Consecuencias

El agente entiende paráfrasis y faltas de ortografía y puede rechazar lo que está fuera de alcance. A cambio depende de un servicio de embeddings para la mejor calidad y tiene que mantener el respaldo.

## Evidencia

Conjunto de 122 preguntas (`tests/data/rag_evaluacion.json`): explícitas, paráfrasis, con faltas, que mezclan dos documentos, "casi iguales" y fuera de alcance, dividido en desarrollo (84) y prueba (38).

| Recuperación | Desarrollo: recall, fuera de alcance rechazadas | Prueba: recall, fuera de alcance rechazadas |
| --- | --- | --- |
| BM25 solo | 68/70 (97,1 %), 13 de 14 | 29/32 (90,6 %), 6 de 6 |
| Híbrido con `embeddinggemma` | 67/70 (95,7 %), 13 de 14 | 30/32 (93,8 %), 6 de 6 |

Antes de sumar la tabla de conceptos coloquiales, la corrección de faltas y la recuperación por cláusula, BM25 solo daba 55/70 y 22/32, y el híbrido 64/70 y 26/32. Después, a partir de un banco de preguntas ajenas al negocio, se ajustaron las palabras que BM25 acepta (se sacaron de la tabla de conceptos palabras genéricas como "funciona" o "escribir", la corrección de faltas exige la misma primera letra, "contacto" necesita una segunda coincidencia y se agregaron las frases que piden un canal) y se sumó una ancla léxica: el documento que BM25 reconoce por una palabra explícita de la pregunta ("reembolso") no se descarta por una diferencia chica de similitud, y un documento mucho más débil que el mejor (menos de 0,4 veces su margen) solo se queda si esa ancla lo respalda. Con eso, el rechazo de preguntas ajenas sin embeddings pasó de 66 de 75 a 73 de 75 (ADR 0013).

Fallos que quedan: paráfrasis lejanas ("mandan a otros países?"), preguntas por el canal de contacto y preguntas que mezclan dos documentos, donde a veces solo se recupera uno. Salvedad: el conjunto lo escribió el autor del código y los márgenes se ajustaron sobre desarrollo con un conjunto chico.
