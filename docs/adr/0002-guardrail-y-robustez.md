# ADR 0002: Guardrail en tres capas y robustez ante intentos de salirse del alcance

Estado: aceptada. Octubre de 2026.

## Contexto

Los documentos 4 y 5 dicen qué no debe resolver el agente: reembolsos mayores a $500, quejas por el trato de un empleado, disputas de facturación y temas legales, que se derivan a soporte@tiendahogar.example. Las reglas son auditables pero no cubren paráfrasis, faltas ni jerga. Además el agente tiene que quedarse en su dominio: no responder tareas ajenas ni obedecer órdenes de cambiar sus reglas.

## Decisión

Tres capas reproducibles; el modelo generativo no clasifica.

1. Reglas (`guardrails.py`) para lo evidente, con tolerancia a faltas y lenguaje coloquial.
2. Embeddings (`semantica.py`) contra frases de ejemplo (`data/anclas.json`), por margen contra la clase "permitida" y no por un umbral absoluto.
3. N-gramas de caracteres como respaldo sin red.

El reembolso exige además un monto mayor a $500 que extrae `montos.py` (`$1.000`, `2k`, `mil quinientos`, `medio millón`, `1.5M`). Exactamente $500 no escala y un rango de días ("5-10 días") no es un monto. Reglas asociadas:

- Pregunta mixta: se responde la parte permitida y se deriva el resto.
- Una pregunta por la regla ("los reembolsos de más de $500, los aprueba un supervisor?") se responde con el Doc 4. Quien niega un reembolso ("no quiero un reembolso, solo saber la garantía") no se deriva. Con algo propio ("quiero", "mi compra") sí.
- Una categoría detectada solo por significado exige una palabra del tema, y un elogio no cuenta como queja.
- Pedir una copia de la factura no es una disputa: se aclara que los documentos no lo cubren y se ofrece derivar si es un reclamo.
- Quinta categoría propia, solo por reglas: un incidente de seguridad con un producto (lesión, descarga, incendio) se deriva a una persona.
- Quien pide hablar con una persona recibe el correo del Doc 5.

La defensa ante lo ajeno es estructural y no depende de que el modelo obedezca: sin documento ni pedido relevante el agente dice que no tiene esa información (así "contame un chiste" no llega al modelo); las órdenes inequívocas de cambiar las reglas se bloquean; una cláusula ajena dentro de una pregunta mixta se saca antes de dársela al modelo; el recuperador no acepta un documento por una coincidencia suelta; la memoria nunca saltea el guardrail; y el texto del cliente no puede abrir un bloque `DOCUMENTOS:` propio dentro del prompt. La detección de inyección se limita a lo inequívoco: es una defensa básica, no una garantía.

## Descartado

Solo reglas (68 % en el primer set), un modelo generativo como clasificador (no reproducible), embeddings sin reglas (sin trazabilidad) y `bge-m3` (1,2 GB; 124 de 130 con 3 falsos positivos, contra 125 con 1 de `embeddinggemma`, 622 MB).

## Evidencia

Set propio de 200 frases, dividido en desarrollo (para ajustar) y prueba. Riesgo detectado, con 0 falsos positivos: reglas solas 86,4 % y 88,1 %; reglas y n-gramas 88,6 % y 95,2 %; reglas y `embeddinggemma` 98,9 % y 97,6 %. Para lo ajeno, 75 ataques en 9 técnicas y un banco de 75 preguntas fuera del negocio: ninguno se obedece ni se responde con un documento, y se rechazan 73 de 75 (las otras 2 son decisiones de diseño). Se probaron Garak (inyecciones codificadas, secuestro de la orden, inyección latente: 256 de 256 en cada familia) y Promptfoo (80 casos en español); mostraron dos defectos que se corrigieron.

Salvedad: el set, las anclas y el banco los escribió la misma persona y varias correcciones salieron de sus fallos, así que las cifras son optimistas (ver el ADR 0006). Las frases de ejemplo están en español.
