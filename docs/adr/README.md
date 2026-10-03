# Registro de decisiones (ADR)

Cada archivo explica una decisión: el problema, lo que se decidió, lo que se descartó y la evidencia. Son cortos a propósito.

| N.º | Decisión |
| --- | --- |
| [0001](0001-alcance-de-la-prueba-tecnica.md) | Alcance: una prueba técnica evaluada por calidad |
| [0002](0002-orquestacion-deterministica-sin-framework.md) | Orquestación determinística, sin framework, y modelo que solo redacta |
| [0003](0003-guardrail-en-tres-capas.md) | Guardrail en tres capas reproducibles |
| [0004](0004-rag-hibrido-y-umbral-por-margen.md) | RAG híbrido (embeddings y BM25) y umbral por margen |
| [0005](0005-consulta-de-pedidos-en-tres-capas.md) | Consulta de pedidos en tres capas |
| [0006](0006-reembolsos-hasta-500.md) | Reembolsos de hasta $500 y monto declarado por el cliente |
| [0007](0007-envios-segun-el-lugar.md) | Plazo de envío según el lugar, con la capital igual a CABA |
| [0008](0008-memoria-de-sesion-y-repreguntas.md) | Memoria de sesión y repreguntas |
| [0009](0009-modelos-locales-y-clientes-sin-sdk.md) | Modelos locales, clientes sin SDK, rendimiento y respaldo offline |
| [0010](0010-estrategia-de-evaluacion.md) | Estrategia de evaluación: desarrollo, prueba y lotes independientes |
| [0011](0011-robustez-ante-intentos-de-sacarlo-de-alcance.md) | Robustez ante intentos de sacar al agente de su alcance |

La visión de conjunto (flujo, módulos y cómo extender el agente) está en [../arquitectura.md](../arquitectura.md).
