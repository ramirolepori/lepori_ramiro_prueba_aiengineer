# ADR 0003: Guardrail en tres capas reproducibles

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Los documentos 4 y 5 dicen qué no debe resolver el agente: reembolsos mayores a $500, quejas por el trato de un empleado, disputas de facturación y temas legales, que se derivan a soporte@tiendahogar.example. Las reglas son rápidas y auditables pero no cubren paráfrasis, faltas ni jerga.

## Decisión

Tres capas reproducibles; el modelo generativo no clasifica.

1. Reglas para lo evidente (`guardrails.py`), con tolerancia a faltas y vocabulario coloquial.
2. Similitud por embeddings (`semantica.py`) contra frases de ejemplo de cada categoría (`data/anclas.json`), por margen contra la clase "permitida" (0,07) y no por un umbral absoluto, para que sirva con otros modelos de embeddings.
3. Respaldo offline por n-gramas de caracteres con TF-IDF, solo librería estándar.

El reembolso exige además un monto mayor a $500 que extrae `montos.py` (`$1.000`, `2k`, `2 lucas`, `mil quinientos`, faltas leves). Exactamente $500 no escala. Un rango de días ("5-10 días") no es un monto.

Reglas asociadas:
- Pregunta mixta: se responde la parte permitida y se deriva el resto. Si lo que se deriva es el reembolso, la parte permitida no repite la política de reembolsos.
- Una categoría detectada solo por significado exige una palabra del tema, y un elogio no cuenta como queja (sin eso, "cuánto es el 15% de 2300?" salía como reembolso).
- Una pregunta por el canal se responde con el correo del documento 5; derivarla también es válido.
- Una devolución de más de $500 con monto explícito pero sin la palabra reembolso se escala por prudencia (decisión propia).
- Inyección: se bloquea solo lo inequívoco ("ignorá tus instrucciones"). Es una defensa básica, no una garantía.

## Alternativas descartadas

- Solo reglas: 68 % en el primer set de riesgo.
- Un modelo generativo como clasificador: no es reproducible, es más lento y depende del modelo.
- Embeddings sin reglas: las reglas dan trazabilidad.
- `bge-m3` (1,2 GB): 124 de 130 con 3 falsos positivos, contra 125 de 130 con 1 de `embeddinggemma` (622 MB).

## Evidencia

Set propio de 200 frases (explícitas, paráfrasis, inglés, mixtas, límite de $500, formatos de monto, faltas), dividido en desarrollo (135, para ajustar) y prueba (65). Riesgo detectado, con 0 falsos positivos en todos los casos:

| Configuración | Desarrollo | Prueba |
| --- | --- | --- |
| Solo reglas | 76/88 (86,4 %) | 37/42 (88,1 %) |
| Reglas y n-gramas (offline) | 78/88 (88,6 %) | 40/42 (95,2 %) |
| Reglas y `embeddinggemma` | 87/88 (98,9 %) | 41/42 (97,6 %) |

Salvedad: el set y las anclas los escribió la misma persona, así que la división no equivale a una prueba independiente (ver el ADR 0010). Las frases de ejemplo están en español y otros idiomas se cubren solo en parte.
