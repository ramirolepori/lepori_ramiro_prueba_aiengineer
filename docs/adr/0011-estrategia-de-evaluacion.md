# ADR 0011: Estrategia de evaluación, desarrollo, prueba y lotes independientes

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Un agente que se ajusta mirando las mismas frases con las que se mide da cifras optimistas. El evaluador corre además un set de escenarios propio que no conocemos, así que hay que medir con frases que el código no haya visto y ser honesto sobre cuánto valen las cifras.

## Decisión

- Conjuntos propios en `tests/data/` (guardrail, pedidos y RAG), cada uno dividido en desarrollo (para ajustar márgenes y reglas) y prueba (sin tocar al ajustar). Tipos de frase: explícitas, paráfrasis, variantes (inglés, mayúsculas, texto largo), "casi iguales pero permitidas", mixtas, límite de $500, formatos de monto, faltas de ortografía y fuera de alcance. Se mide con `python -m tiendahogar.evaluacion` (guardrail), `evaluacion pedidos` y `evaluacion rag`.
- Lotes independientes: frases escritas por una persona que no escribió el código ni las anclas (`python -m tiendahogar.independiente`). Cada línea lleva un código de lo esperado (por ejemplo `R` reembolso de más de $500, `T` queja de trato, `F` facturación, `L` legal, `OK` no derivar, `P=1001` pregunta por un pedido con su número, `PX=DRO-1002` identificador con formato raro, `D=garantia+devoluciones` documentos esperados, `X` fuera de alcance). Un `~` al final indica que derivar también es válido (preguntas por el canal de contacto).
- Orígenes que se reportan por separado: las frases de Ramiro, un lote 2 escrito por Claude con el estilo y la jerga de las de Ramiro (lunfardo y colombianismos) y variantes automáticas (sin tildes, mayúsculas, errores de tipeo). Las frases del lote 2 no son independientes (las escribió quien escribió el código) y sirven como material de desarrollo.
- Regla: la primera medición de un lote es la limpia. Después de corregir fallos a partir de un lote, sus cifras pasan a ser optimistas y la prueba vuelve a ser un lote nuevo. Las correcciones se hacen con reglas generales y no copiando frases.
- Además, los 425 tests de `pytest` fijan los comportamientos (ver la sección de pruebas de `SUBMISSION.md`).

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

Pendiente: un lote nuevo y definitivo escrito por Ramiro, que se mide una sola vez antes de tocar nada.
