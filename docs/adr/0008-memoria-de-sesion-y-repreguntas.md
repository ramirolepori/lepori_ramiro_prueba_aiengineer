# ADR 0008: Memoria de sesión y repreguntas

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Sin memoria, cuando falta un dato el agente tiene que volcar todo el documento ("Soy de Zapala" recibe los tres plazos) o inventar. Con memoria puede repreguntar y dar una respuesta certera: el lugar para un envío, el monto para un reembolso, el número para un pedido.

## Decisión

- Estado estructurado, no historial de mensajes (`sesion.py`). Es el patrón de slot filling de los chatbots de tareas ([Rasa Forms](https://rasa.com/docs/rasa/forms)): se guarda qué dato está pendiente (lugar, confirmación de lugar, monto, número de pedido, antigüedad de la compra o reclamo), la consulta incompleta y cuántas veces se repreguntó. No necesita al modelo ni guarda texto del cliente.
- La respuesta se lee con los mismos extractores del agente. Si calza, se arma la consulta completa y pasa por el flujo normal, guardrail incluido: la memoria no es un atajo, y un mensaje para derivar o una inyección se tratan como tales aunque haya algo pendiente.
- La memoria es opcional y la maneja quien llama: `responder(pregunta)` no recuerda nada, también si se reutiliza el agente, y `responder(pregunta, sesion)` sí. El chat interactivo crea una sesión (`--sin-memoria` la desactiva).
- La repregunta trae la respuesta condicional, para que sirva sola si el evaluador manda un único mensaje.
- Límites: lo pendiente se olvida a los 5 mensajes y se repregunta como máximo 2 veces por dato; después se responde con la información completa, pero lo pendiente sigue abierto. Un mensaje largo, con pregunta o de otro tema descarta lo pendiente.
- Con algo pendiente, un saludo, un agradecimiento o algo ajeno a la tienda se contesta y se vuelve a pedir el dato; una despedida lo cierra.
- Lo que el cliente ya dijo se puede volver a preguntar ("cuál fue la orden que te pasé?", "en qué ciudad dije que estaba?", "qué monto te dije?"). Se guarda un diccionario chico (`recuerdos.py`) con el pedido (normalizado a ORD-XXXX), el lugar (solo uno reconocido) y el monto, pasados por los extractores. Las respuestas son plantillas fijas; sin dato dice que todavía no se lo dijeron. Nunca se guarda ni se repite texto libre y cada sesión es independiente.
- Reembolso sin monto: se pregunta el monto (ADR 0006).
- Factura o comprobante que no se entregó: los documentos no dicen qué hacer, así que el agente lo dice y pregunta "¿Querés hacer un reclamo?". Con un sí se deriva como disputa de facturación y con un no se cierra.
- Antigüedad de la compra: se pregunta "hace cuánto lo compraste" solo si la pregunta habla de algo propio, toca solo devoluciones y garantía y no dice cuándo compró. No se pregunta en preguntas de política general, productos que no se devuelven, ni cuando el cliente da la causa de la falla. La respuesta se une a la consulta ("Antigüedad: hace 3 semanas") y el flujo normal decide con las cifras del documento.

## Alternativas descartadas

- Guardar el historial completo y dárselo al modelo: más tokens, depende del modelo y guarda texto del cliente.
- Memoria implícita dentro del agente: contamina escenarios independientes.
- Un almacén externo con vencimiento (Redis): fuera de alcance (ADR 0001).

## Consecuencias

El agente repregunta en vez de volcar documentos y la derivación sigue siendo determinística. Hallazgo al probar: un mensaje corto para derivar ("los voy a denunciar") se tomaba como intento de respuesta; ahora el guardrail corre primero. Casos en `tests/test_sesion.py`.
