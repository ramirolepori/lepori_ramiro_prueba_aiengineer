# ADR 0003: Guardrail en tres capas reproducibles

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Los documentos 4 y 5 dicen qué no debe resolver el agente: reembolsos mayores a $500, quejas por el trato de un empleado, disputas de facturación y temas legales. Esos casos se derivan a soporte@tiendahogar.example. Unas reglas con expresiones regulares son rápidas y auditables, pero no cubren paráfrasis ("regresen la plata"), faltas de ortografía ni jerga. Ante la duda se escala de más, pero con un límite: la tasa de falsos positivos también tiene que ser baja.

## Decisión

Tres capas, todas reproducibles (mismo texto, mismo resultado). El modelo de lenguaje generativo no clasifica.

1. Reglas para lo evidente (`guardrails.py`). Incluyen coincidencia aproximada para la intención de reembolso ("rembolso", "debuelvan") y vocabulario coloquial de agresión y de cobros ("me echó", "me chuparon la plata dos veces").
2. Similitud semántica por embeddings (`semantica.py`). La pregunta se compara con frases de ejemplo de cada categoría (`data/anclas.json`) y se decide por margen contra la clase "permitida", no por un umbral absoluto: así el método es portable entre modelos de embeddings, que tienen escalas distintas. Margen elegido: 0,07 (estable entre 0,06 y 0,08). Los embeddings se piden por HTTP al endpoint `/v1/embeddings`, sin librerías nuevas.
3. Respaldo offline por n-gramas de caracteres con TF-IDF, solo librería estándar, que tolera tildes y faltas.

El reembolso exige además un monto explícito mayor a $500, que siempre extrae el parser de montos (`montos.py`): entiende `$1.000`, `1,000`, `2k`, `2 lucas`, `mil quinientos`, `USD600` y faltas leves en números escritos. Un reembolso de exactamente $500 no escala, porque el documento dice "mayores a $500".

Reglas de diseño asociadas:

- Pregunta mixta: se responde primero la parte permitida (con documentos o con la tool) y después se deriva el resto. Las cláusulas se separan por puntuación y conectores sin cortar decimales como `$1.000`. Con más de un motivo se usa el mensaje del primero, porque el canal es el mismo.
- Una pregunta por el canal ("con quién hablo por un tema legal?") se responde con el correo del documento 5. Si el guardrail la deriva igual, también es válido, porque da el mismo correo.
- Una categoría detectada solo por significado exige además una palabra del tema (de plata, de persona o de ley, también en inglés), y una frase que elogia al empleado no cuenta como queja. Sin ese requisito, "Cuánto es el 15% de 2300?" salía como reembolso de más de $500 y "se me quemó la plancha" como queja.
- Inyección de prompt: se limita a lo inequívoco ("ignorá tus instrucciones", "mostrame tu prompt"). Es una defensa básica y no una garantía; si sobra tiempo se puede reforzar.
- Devolución de un producto de más de $500 sin la palabra "reembolso" ("devolver una estufa de $900"): se escala solo cuando hay un monto explícito. Esta regla no está en los documentos y es una decisión propia.

## Alternativas descartadas

- Solo reglas: cubren el 68 % del primer set de riesgo y fallan en paráfrasis, inglés y faltas.
- Un modelo de lenguaje como clasificador: no es reproducible, es más lento y depende del modelo. Se podría sumar más adelante solo para los casos de baja confianza.
- Reemplazar las reglas por embeddings: las reglas se mantienen para lo evidente y dan trazabilidad (la traza dice si decidió una regla o la capa semántica).
- Modelo de embeddings `bge-m3` (1,2 GB): quedó 124 de 130 con 3 falsos positivos contra 125 de 130 con 1 de `embeddinggemma` (622 MB), que fue el elegido.

## Consecuencias

El guardrail corre antes del modelo, así que no depende de que el modelo obedezca, y se prueba sin red. Las frases de ejemplo y las reglas se escribieron en español: otros idiomas se cubren solo parcialmente.

## Evidencia

Set propio de 200 frases de riesgo, normales y "casi iguales" (explícitas, paráfrasis, variantes en inglés y mayúsculas, mixtas, límite de $500, formatos de monto y faltas de ortografía), dividido en desarrollo (135, para ajustar el margen) y prueba (65, sin tocar al ajustar). Riesgo detectado y falsos positivos:

| Configuración | Desarrollo | Prueba |
| --- | --- | --- |
| Solo reglas | 74/88 (84,1 %), 0 de 47 | 37/42 (88,1 %), 0 de 23 |
| Reglas y n-gramas (offline) | 77/88 (87,5 %), 0 de 47 | 40/42 (95,2 %), 0 de 23 |
| Reglas y `embeddinggemma` | 87/88 (98,9 %), 0 de 47 | 41/42 (97,6 %), 0 de 23 |

Salvedad: el set y las anclas los escribió la misma persona en la misma sesión, así que la división no equivale a una prueba independiente. Las mediciones con frases ajenas están en el ADR 0011.

Fallo conocido con embeddings en desarrollo: "boy a tomar acciones lejales" (faltas de ortografía en una frase legal).

Fuentes consultadas para el diseño en capas: [Semantic Router](https://pub.towardsai.net/semantic-router-the-ai-traffic-controller-4a55f7fe7c35), [comparación de guardrails](https://blog.premai.io/production-llm-guardrails-nemo-guardrails-ai-llama-guard-compared) y [Building Guardrails for Large Language Models](https://arxiv.org/pdf/2402.01822).
