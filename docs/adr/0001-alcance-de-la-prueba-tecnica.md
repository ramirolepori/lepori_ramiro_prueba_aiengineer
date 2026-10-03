# ADR 0001: Alcance, una prueba técnica evaluada por calidad

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El agente de TiendaHogar es la prueba técnica de un proceso de selección. El enunciado dice que no se evalúa la velocidad sino la calidad de las decisiones, y que además de la suite propia el evaluador corre un set de escenarios que no conocemos. Los registros de decisiones suelen usarse en proyectos largos con varios desarrolladores, algunos asistidos por IA, y conviene no copiar ese peso a un ejercicio acotado.

## Decisión

- Se diseña para ser evaluado, no para producción. Cada decisión se toma para este alcance y se prueba o se mide.
- La sección de producción de `SUBMISSION.md` describe cómo se mapearía el agente a Foundry, Databricks, Apigee y Kafka, pero no se implementa infraestructura (sin Redis, almacenes de hilos ni servicios).
- La documentación se limita a lo que aporta: `SUBMISSION.md` con la plantilla exacta del enunciado, este registro de decisiones con un ADR por decisión que cambia el diseño, y un documento de arquitectura (`docs/arquitectura.md`). No se agregan changelogs, hojas de ruta ni un ADR por cada ajuste chico.
- Lo que no alcanza a hacerse queda declarado en las limitaciones, sin inventar mediciones ni horas.

## Alternativas descartadas

- Pensar el diseño para producción (colas, estado distribuido, vencimiento por reloj): suma superficie y riesgo sin que nadie lo evalúe.
- Todo el detalle dentro de `SUBMISSION.md`: la plantilla pide secciones concisas, y el detalle las volvía ilegibles.

## Consecuencias

El diseño es más simple y cada pieza se puede explicar y probar. A cambio, hay decisiones que en un sistema real serían otras (por ejemplo la memoria vive en el proceso y no en un almacén compartido); cada ADR lo dice cuando aplica.
