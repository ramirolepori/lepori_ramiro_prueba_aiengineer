# ADR 0011: Estrategia de evaluación, desarrollo, prueba y lotes independientes

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Un agente que se ajusta mirando las mismas frases con las que se mide da cifras optimistas. El evaluador corre además un set de escenarios propio que no conocemos, así que hay que medir con frases que el código no haya visto y ser honesto sobre cuánto valen las cifras.

## Decisión

- Conjuntos propios en `tests/data/` (guardrail, pedidos y RAG), cada uno dividido en desarrollo (para ajustar márgenes y reglas) y prueba (sin tocar al ajustar). Tipos de frase: explícitas, paráfrasis, variantes (inglés, mayúsculas, texto largo), "casi iguales pero permitidas", mixtas, límite de $500, formatos de monto, faltas de ortografía y fuera de alcance. Se mide con `python -m tiendahogar.evaluacion` (guardrail), `evaluacion pedidos` y `evaluacion rag`.
- Lotes independientes: frases escritas por una persona que no escribió el código ni las anclas (`python -m tiendahogar.independiente`). Cada línea lleva un código de lo esperado (por ejemplo `R` reembolso de más de $500, `T` queja de trato, `F` facturación, `L` legal, `OK` no derivar, `P=1001` pregunta por un pedido con su número, `PX=DRO-1002` identificador con formato raro, `D=garantia+devoluciones` documentos esperados, `X` fuera de alcance). Un `~` al final indica que derivar también es válido (preguntas por el canal de contacto).
- Orígenes que se reportan por separado: las frases de Ramiro, un lote 2 escrito por Claude con el estilo y la jerga de las de Ramiro (lunfardo y colombianismos) y variantes automáticas (sin tildes, mayúsculas, errores de tipeo). Las frases del lote 2 no son independientes (las escribió quien escribió el código) y sirven como material de desarrollo.
- Regla: la primera medición de un lote es la limpia. Después de corregir fallos a partir de un lote, sus cifras pasan a ser optimistas y la prueba vuelve a ser un lote nuevo. Las correcciones se hacen con reglas generales y no copiando frases.
- Además, los 782 tests de `pytest` fijan los comportamientos (ver la sección de pruebas de `SUBMISSION.md`).

## Alternativas descartadas

- Medir sobre las mismas frases con las que se ajusta: cifras optimistas sin valor como evidencia.
- Un único conjunto grande sin división: no deja ningún dato sin tocar.

## Consecuencias

Las cifras se reportan con su salvedad. El valor de las mediciones sobre frases ajenas es mayor que el de las propias, y los fallos que aparecieron en ellas (agresiones físicas, cobros en coloquial, jerga de montos, identificadores raros, número de pedido tras "compra") se corrigieron de forma general.

## Evidencia

Primera medición de cada lote, antes de corregir, y estado actual (riesgo detectado y falsos positivos con reglas y embeddings; extracción de números; documentos del híbrido):

| Lote | Primera medición | Estado actual |
| --- | --- | --- |
| Frases de Ramiro (48) | riesgo 8/10, 2 falsos positivos; números 5/9; identificadores raros 0/2; documentos 16/19 | riesgo 10/10, 0 falsos positivos; números 9/9; raros 2/2; documentos 17/19 |
| Lote 2 (118) | riesgo 42/44, 6 falsos positivos; números 15/16; raros 0/3; documentos 24/28 | riesgo 44/44, 0 falsos positivos; números 16/16; raros 3/3; documentos 28/28 |
| Variantes automáticas (174) | no medidas antes | riesgo 38/38, 0 de 132 falsos positivos; números 29/29; raros 7/7; documentos 66/73 |

En el conjunto de desarrollo y el de prueba no hubo regresión (ADR 0003 y ADR 0004).

Lote 3 de Ramiro (42 frases escritas el 3 de octubre, `tests/data/independiente_lote3.txt`): es la única medición limpia del proyecto, hecha una sola vez antes de tocar nada. Con embeddings: riesgo detectado 8 de 10 con 0 falsos positivos en 29, números de pedido 5 de 5, documentos correctos 15 de 15, preguntas ajenas rechazadas 8 de 8 y un identificador con formato raro respondido bien 0 de 1. Sin embeddings, el riesgo daba 5 de 10 y 6 de 10. Fallos y qué se hizo:
- `DOR--1002` dentro de "ordené una licuadora (DOR--1002)": el agente decía "no tengo esa información" en vez de "no encontré ese identificador". Ahora se reconoce un código con doble guion o dentro de un paréntesis cuando la frase habla de un pedido.
- Quejas de trato dichas de otra forma ("lo hizo tan mal que mi novia salió llorando", "me tiró un vaso de agua en la cara", "actitudes que me faltaron el respeto"): reglas nuevas, de modo que ya no dependen de los embeddings.
- Las dos frases que Ramiro agrupó como "temas legales" ("no me dieron factura de compra", "cómo hago valer mi garantía si no recibí comprobante"): no mencionan un reclamo legal y los documentos no dicen qué hacer. Decisión de Ramiro: el agente responde que no tiene esa información (y da lo que sí dice la garantía si preguntó por ella), pregunta si quiere hacer un reclamo y, si responde que sí, deriva a una persona.
- Lectura de las respuestas completas con el modelo: un agradecimiento ("estoy muy conforme con la compra") recibía la política de devoluciones y el pedido del número de pedido; ahora recibe un agradecimiento. "A la Quiaca" no estaba en el diccionario de lugares (se agregaron unos cien); un producto "hecho solo para mí" preguntaba hace cuánto se compró en vez de decir que no se devuelve; y las respuestas mostraban la indicación interna de los documentos ("el asistente de IA no debe intentar resolver estos casos"), que ahora se saca de lo que ve el cliente.
Después de estas correcciones el lote 3 da riesgo 8 de 8 (con las dos frases ambiguas resueltas por la pregunta de reclamo), identificador raro 1 de 1 y las demás cifras iguales, pero ya no es una medición limpia. El siguiente lote que haga falta tiene que ser nuevo.
