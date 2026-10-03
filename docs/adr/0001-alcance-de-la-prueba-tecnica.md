# ADR 0001: Alcance, una prueba técnica evaluada por calidad

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El agente es la prueba técnica de un proceso de selección. El enunciado dice que no se evalúa la velocidad sino la calidad de las decisiones, y que el evaluador corre además un set de escenarios que no conocemos.

## Decisión

- Se diseña para ser evaluado, no para producción. Cada decisión se prueba o se mide, y lo que no alcanza a hacerse queda declarado en las limitaciones de `SUBMISSION.md`.
- La producción (Foundry, Databricks, Apigee, Kafka) se describe en `SUBMISSION.md`, sin implementar infraestructura.
- Documentación mínima: `SUBMISSION.md` con la plantilla del enunciado, `docs/arquitectura.md` y un ADR corto por cada decisión que cambia el diseño.

## Alternativas descartadas

- Diseñar para producción (colas, estado distribuido, vencimiento por reloj): suma superficie y riesgo sin que nadie lo evalúe.
- Todo el detalle dentro de `SUBMISSION.md`: la plantilla pide secciones concisas.

## Consecuencias

El diseño es más simple y cada pieza se puede explicar y probar. En un sistema real algunas decisiones serían otras (por ejemplo la memoria viviría en un almacén compartido).
