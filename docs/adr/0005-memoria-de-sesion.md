# ADR 0005: Memoria de sesión y repreguntas

Estado: aceptada. Octubre de 2026.

## Contexto

Sin memoria, cuando falta un dato el agente tiene que volcar el documento entero ("Soy de Zapala" recibiría los tres plazos) o inventar. Con memoria repregunta y responde con certeza: el lugar para un envío, el monto para un reembolso, el número o la fecha para una devolución.

## Decisión

- Estado estructurado, no historial (`sesion.py`): qué dato está pendiente, la consulta incompleta y cuántas veces se repreguntó. Es el patrón de slot filling de los chatbots de tareas. No necesita al modelo ni guarda texto del cliente.
- La respuesta se lee con los mismos extractores del agente, y si calza se arma la consulta completa y pasa por el flujo normal, guardrail incluido: la memoria no es un atajo.
- Es opcional y la maneja quien llama: `responder(pregunta)` no recuerda nada y `responder(pregunta, sesion)` sí. Cada repregunta trae la respuesta condicional, para que sirva sola si el evaluador manda un único mensaje.
- Límites: lo pendiente se olvida a los 5 mensajes y se repregunta como máximo 2 veces por dato. Con algo pendiente, un saludo o algo ajeno se contesta y se vuelve a pedir el dato; una despedida lo cierra.
- Datos que se piden: lugar (y su confirmación), monto, número de pedido y hace cuánto compró. En lugar de la fecha el cliente puede dar el número de pedido: se consulta la tool y, según el estado, se pregunta la fecha (entregado), se avisa que todavía no figura como entregado (procesando o en tránsito) o que fue cancelado. "Quiero hacer una devolución" dispara esta pregunta y el hilo no se pierde. Si el cliente da otro dato (un pedido cuando se esperaba el monto, "la compré en liquidación" cuando se esperaba la fecha), se usa.
- Lo que el cliente ya dijo se puede volver a preguntar ("qué orden te pasé?"). Se guarda un diccionario chico (`recuerdos.py`) con pedido, lugar y monto ya normalizados, y las respuestas son plantillas fijas. Nunca se guarda ni se repite texto libre.
- Factura o comprobante que no se entregó: los documentos no dicen qué hacer, así que se dice y se pregunta "¿Querés hacer un reclamo?". Con un sí se deriva y con un no se cierra.

## Descartado

Guardar el historial y dárselo al modelo (más tokens, depende del modelo, guarda texto del cliente), una memoria implícita dentro del agente (contamina escenarios independientes) y un almacén externo con vencimiento (fuera de alcance).

## Límite que queda

La memoria cubre datos pendientes, no sigue la charla: "y si estuviera usada?" sin contexto se responde como una pregunta nueva. Casos en `tests/test_sesion.py`.
