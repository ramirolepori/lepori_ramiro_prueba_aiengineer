# Registro de decisiones de arquitectura (ADR)

Cada archivo explica una decisión: qué problema había, qué se decidió, qué se descartó y qué consecuencias tiene. Sirven para entender el porqué del diseño sin releer el código, y para que quien retome el proyecto (una persona o una IA) sepa qué no cambiar sin revisar antes el motivo.

Formato: estado, contexto, decisión, alternativas descartadas, consecuencias y, cuando hay, la evidencia medida. Si una decisión cambia, no se reescribe: se agrega un ADR nuevo que la reemplaza y el viejo queda marcado como reemplazado.

| N.º | Decisión | Estado |
| --- | --- | --- |
| [0001](0001-alcance-de-la-prueba-tecnica.md) | Alcance: una prueba técnica evaluada por calidad | Aceptada |
| [0002](0002-orquestacion-deterministica-sin-framework.md) | Orquestación determinística, sin framework | Aceptada |
| [0003](0003-guardrail-en-tres-capas.md) | Guardrail en tres capas reproducibles | Aceptada |
| [0004](0004-rag-hibrido-y-umbral-por-margen.md) | RAG híbrido (embeddings y BM25) y umbral por margen | Aceptada |
| [0005](0005-consulta-de-pedidos-en-tres-capas.md) | Consulta de pedidos en tres capas | Aceptada |
| [0006](0006-reembolsos-hasta-500.md) | Reembolsos de hasta $500 y monto declarado por el cliente | Aceptada |
| [0007](0007-envios-segun-el-lugar.md) | Plazo de envío según el lugar, con la capital igual a CABA | Aceptada |
| [0008](0008-memoria-de-sesion-y-repreguntas.md) | Memoria de sesión y repreguntas | Aceptada |
| [0009](0009-modelos-locales-y-clientes-sin-sdk.md) | Modelos locales de referencia y clientes HTTP sin SDK | Aceptada |
| [0010](0010-el-modelo-solo-redacta.md) | El modelo solo redacta: validación de salida, notas y cobertura por código | Aceptada |
| [0011](0011-estrategia-de-evaluacion.md) | Estrategia de evaluación: desarrollo, prueba y lotes independientes | Aceptada |
| [0012](0012-rendimiento-y-respaldo-offline.md) | Rendimiento por etapa y respaldo offline | Aceptada |

La visión de conjunto (flujo, módulos y cómo extender el agente) está en [../arquitectura.md](../arquitectura.md).
