# ADR 0001: Alcance y orquestación

Estado: aceptada. Octubre de 2026.

## Contexto

Es una prueba técnica: el enunciado dice que se evalúa la calidad de las decisiones, no la velocidad, y que el evaluador corre escenarios propios. Con `qwen2.5:7b` se vio que un modelo chico omite aclaraciones obligatorias, deforma cifras, inventa citas, cubre una sola de dos políticas y razona mal cuentas simples (el plazo de 30 días).

## Decisión

- Se diseña para ser evaluado, no para producción. La producción (Foundry, Databricks, Apigee, Kafka) se describe en `SUBMISSION.md` sin implementarla, y lo que no se alcanzó a probar queda en las limitaciones.
- El código decide el flujo y el modelo solo redacta con lo recuperado: inyección, guardrail, tool de pedidos, RAG, redacción y validación de la salida. Sin LangChain, LangGraph ni tool calling decidido por el modelo. El esquema de la tool está en `pedidos.py` por si se quiere exponer.
- Lo obligatorio lo resuelve el código antes o después del modelo: la regla de los $500, el pedido del número de pedido, el plazo de devolución y de garantía según el tiempo que dice el cliente (`plazos.py`, también cuando mezcla ambas: "mi lavadora tiene 8 meses y se rompió, ¿puedo devolverla?", y cuando hay un número de pedido, que aporta el estado y el producto: el modelo no redacta esas respuestas), el plazo de envío según el lugar, el canal humano, y la cobertura de dos políticas cuando la pregunta nombra ambas.
- Validación de la salida: se descarta (y se usa el modo offline) una respuesta con cifras o correos que no estaban en el contexto, demasiado corta, con promesas ("fue aprobado", "te lo reparamos gratis"), con un "sí" sobre devolver liquidación, con un remedio que los documentos no ofrecen (arreglo, reemplazo, canje) o con cuatro o más palabras largas sin respaldo. Es una red de seguridad calibrada a mano, no una garantía.

## Descartado

- Un framework de agentes: con 5 documentos, una tool y un flujo lineal agrega capas. Sería razonable con un corpus o unas tools mucho mayores.
- Tool calling decidido por el modelo: menos predecible justo en los casos críticos.
- Diseñar para producción (colas, estado distribuido): superficie y riesgo que nadie evalúa.

## Consecuencias

El comportamiento crítico es el mismo con cualquier modelo y se prueba sin red. El modo offline es una salida válida. Costo: cada capacidad nueva es código que hay que probar.
