# ADR 0008: Memoria de sesión y repreguntas

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Sin memoria, cuando falta un dato el agente tiene que volcar todo el documento ("Soy de Zapala" recibe los tres plazos) o inventar. Con memoria puede repreguntar y dar una respuesta certera y concisa: el lugar para un envío, el monto para un reembolso, el número para un pedido.

## Decisión

- Estado estructurado, no historial de mensajes (`sesion.py`). La sesión guarda qué dato está pendiente (lugar, confirmación de lugar, monto o número de pedido), la consulta que quedó incompleta y cuántas veces se repreguntó. Es el patrón de slot filling de los chatbots de tareas ([Rasa Forms](https://rasa.com/docs/rasa/forms): se define qué dato falta, se pregunta y el formulario se cierra al completarse) y la recomendación de tratar la memoria como un sistema estructurado y no como una lista plana de mensajes. Es más chico, no necesita al modelo y no guarda texto del cliente.
- La respuesta del cliente se lee con los mismos extractores del agente (`lugares`, `montos`, `pedidos`). Si calza, se arma la consulta completa y pasa por el flujo normal, guardrail incluido: la memoria no es un atajo. Un mensaje que debe derivarse (legal, trato...) o que es una inyección se trata como tal aunque haya algo pendiente.
- La memoria es opcional y la maneja quien llama. `responder(pregunta)` sin sesión no recuerda nada, también si se reutiliza el agente, lo que evita que un escenario contamine al siguiente. `responder(pregunta, sesion)` sí recuerda. El chat interactivo crea una sesión.
- La repregunta trae la respuesta condicional, para que sirva sola cuando el evaluador manda un único mensaje (el agente responde: `No ubico "Zapala". ¿Es una ciudad de Argentina fuera de la Ciudad de Buenos Aires (CABA)? Si es así, el envío tarda 5-7 días hábiles.`).
- Repreguntar cuando el lugar es ambiguo ("Buenos Aires"): con un sí es la Ciudad (2-3 días hábiles), con un no es otra localidad de la provincia (5-7).
- Reembolso sin monto: se pregunta en vez de mostrar la política, que no hace falta si se va a repreguntar (ADR 0006).
- Límites: lo pendiente se olvida a los 5 mensajes (sin tiempo de vida por reloj) y se repregunta como máximo 2 veces por dato. Después se responde con la información completa sin insistir, pero lo pendiente sigue abierto hasta los 5 mensajes: si el cliente da el dato después, se usa. Un mensaje largo, con pregunta o de otro tema descarta lo pendiente.
- El modelo no maneja la memoria: el estado, la extracción y la decisión de repreguntar son código.
- Alcance: lugar, monto y número de pedido. Queda pendiente, para el final si hay tiempo, preguntar hace cuánto compró en garantías y devoluciones.

## Alternativas descartadas

- Guardar el historial completo y dárselo al modelo: más tokens, más lento, depende del modelo y guarda texto del cliente.
- Memoria implícita dentro del agente: contamina escenarios independientes si el evaluador reutiliza la instancia.
- Un almacén externo con vencimiento por tiempo (Redis, almacenes de hilos): fuera de alcance de una prueba técnica (ADR 0001); en producción sería el equivalente.

## Consecuencias

El agente repregunta en vez de volcar documentos, y la derivación sigue siendo determinística. Hallazgo al probar: un mensaje corto para derivar ("los voy a denunciar") se tomaba como intento de respuesta y se repreguntaba antes del guardrail; ahora el guardrail corre primero. Los casos están en `tests/test_sesion.py` (conversaciones de varios turnos: dato dado, dado tarde, sí y no, cambio de tema, límite de repreguntas, olvido a los 5 mensajes, sesiones que no se mezclan, guardrail e inyección dentro de una sesión).
