# ADR 0010: Estrategia de evaluación, desarrollo, prueba y lotes independientes

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Un agente que se ajusta mirando las mismas frases con las que se mide da cifras optimistas, y el evaluador corre un set que no conocemos. Hay que medir con frases que el código no vio y ser honesto sobre cuánto valen las cifras.

## Decisión

- Conjuntos propios en `tests/data/` (guardrail, pedidos y RAG), cada uno dividido en desarrollo (para ajustar) y prueba (sin tocar al ajustar). Se miden con `python -m tiendahogar.evaluacion`, `evaluacion pedidos` y `evaluacion rag`.
- Lotes independientes: frases de otra persona (`python -m tiendahogar.independiente medir`), cada una con un código de lo esperado (`R`, `T`, `F`, `L` para derivar, `OK`, `P=1001`, `D=garantia`, `X`).
- La primera medición de un lote es la limpia. Después de corregir sus fallos las cifras pasan a ser optimistas y la prueba vuelve a ser un lote nuevo. Las correcciones son reglas generales, no frases copiadas.
- Los lotes de Claude (lote 2 y variantes automáticas) no son independientes: los escribió quien escribió el código, y sirven como material de desarrollo.

## Alternativas descartadas

- Medir sobre las mismas frases con las que se ajusta, o con un único conjunto sin división: cifras sin valor como evidencia.

## Evidencia

Primera medición de cada lote, antes de corregir, y estado actual (riesgo detectado y falsos positivos, con embeddings):

| Lote | Primera medición | Estado actual |
| --- | --- | --- |
| Frases de Ramiro (48) | riesgo 8/10, 2 falsos positivos; números 5/9 | riesgo 10/10, 0 falsos positivos; números 9/9 |
| Lote 2 (118) | riesgo 42/44, 6 falsos positivos; números 15/16 | riesgo 44/44, 0 falsos positivos; números 16/16 |
| Variantes automáticas (174) | no medidas antes | riesgo 38/38, 0 de 132 falsos positivos |

Lote 3 de Ramiro (42 frases, `tests/data/independiente_lote3.txt`): es la única medición limpia, hecha una sola vez antes de tocar nada. Con embeddings: riesgo 8 de 10 con 0 falsos positivos en 29, números de pedido 5 de 5, documentos 15 de 15, preguntas ajenas rechazadas 8 de 8 y un identificador raro 0 de 1. Sin embeddings, el riesgo daba 5 y 6 de 10. Los fallos y lo que se hizo:
- Un identificador raro dentro de una frase ("DOR--1002") respondía "no tengo esa información": ahora se reconoce cuando la frase habla de un pedido.
- Quejas de trato dichas de otra forma ("me tiró un vaso de agua en la cara"): reglas nuevas.
- Factura o comprobante no entregado: los documentos no dicen qué hacer, así que el agente lo dice y pregunta si quiere hacer un reclamo (ADR 0008). Decisión de Ramiro.
- Al leer las respuestas completas: un agradecimiento recibía una política (ahora se agradece), faltaban lugares en el diccionario (se agregaron unos cien), un producto hecho a pedido preguntaba la antigüedad y las respuestas mostraban la indicación interna de los documentos (ahora se saca).

Tras las correcciones el lote 3 da riesgo 8 de 8 e identificador raro 1 de 1, pero ya no es limpio: el siguiente lote tiene que ser nuevo.

Una evaluación externa posterior (otra persona leyendo el repositorio) encontró dos defectos que los tests propios no veían: un rango de días ("5-10 días") se tomaba como un monto de $5, y un reembolso derivado repetía una nota de "no hace falta supervisor". Se corrigieron y tienen test (`tests/test_criticos.py`).
