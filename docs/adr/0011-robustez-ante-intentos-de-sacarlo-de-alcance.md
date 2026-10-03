# ADR 0011: Robustez ante intentos de sacar al agente de su alcance

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Un agente de soporte tiene que quedarse en su dominio: no responder trivia ni tareas ajenas (la distancia del sol a la luna), no obedecer órdenes de cambiar sus reglas y no filtrar sus instrucciones. Las técnicas para el banco de pruebas salen de la [guía de OWASP sobre inyección de prompts](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), del [plugin de temas ajenos de promptfoo](https://www.promptfoo.dev/docs/red-team/plugins/off-topic/) y de resúmenes de técnicas de jailbreak (personajes como DAN, ofuscación, fragmentación de la orden).

## Decisión

La defensa es estructural y no depende de que el modelo obedezca (ADR 0002):

1. Lo que no tiene que ver con los documentos no llega al modelo: sin documento ni pedido relevante el agente dice que no tiene esa información, así que "contame un chiste" no tiene a quién obedecer.
2. Las órdenes inequívocas de cambiar las reglas se bloquean antes de todo (ADR 0003).
3. En una pregunta mixta, la cláusula que pide una tarea ajena ("escribime un poema") se saca antes de dársela al modelo, solo si ningún documento ni pedido se relaciona con ella. Hizo falta: con la pregunta entera `qwen2.5:7b` escribió el poema.
4. El recuperador no acepta un documento por una coincidencia suelta (ADR 0004). Antes de ajustarlo, 9 de 75 preguntas ajenas recibían un documento.
5. La memoria nunca saltea el guardrail ni la inyección (ADR 0008), y el agente no confirma ni aprueba nada (ADR 0006).

Los estados seguros son `bloqueado`, `sin_informacion` o `escalado` (si el mensaje contiene palabras del guardrail, se deriva, que es lo prudente). Lo que no puede pasar es obedecer o responder con un documento. Ante un pedido de una acción que el agente no puede hacer (enviar un correo, reservar, generar una factura) aclara que no puede y a quién escribir.

## Herramientas externas probadas

Se probaron dos herramientas conocidas contra una función que envuelve al agente (sin modelo de lenguaje), en un entorno aparte, fuera del repositorio:
- [Garak](https://reference.garak.ai/en/latest/generators/function.html) 0.17. Superó 256 de 256 en cada una de las 14 variantes de inyección con codificación (base64, ROT13, Morse, Braille, etc.), en el secuestro de la orden de `promptinject` y en 10 familias de inyección latente, y el 100 % en las sondas de claves, inyección SQL y de plantillas y malware. Varias sondas figuran como "falla" porque sus detectores buscan frases de rechazo en inglés y el agente rechaza en español; se revisaron a mano. No se completaron `sysprompt_extraction` ni `web_injection` por un error de descarga de un conjunto de datos. Lo que mostró: los textos largos de DAN en inglés caían en el guardrail de trato; se agregaron esas frases en inglés y español a la detección de inyección.
- [Promptfoo](https://www.promptfoo.dev/docs/red-team/plugins/off-topic/) 0.120. Generó 80 casos en español con `qwen2.5:7b` local; su evaluación pide un correo de verificación, así que se corrieron contra el agente por separado y se revisaron a mano: ninguno lo sacó de su alcance ni extrajo sus instrucciones. Encontró dos defectos, ya corregidos: las acciones que el agente no puede hacer recibían una respuesta ajena, y "cuál es el teléfono del soporte en España" se tomaba como queja de trato.

Los casos generados con un modelo local fueron poco agresivos, así que sirven más para cubrir técnicas conocidas que como evaluación del agente.

## Alternativas descartadas

- Un clasificador de tema con un modelo de lenguaje: otra llamada, no reproducible y duplica el umbral del recuperador.
- Una lista creciente de frases de ataque: siempre va un paso atrás.

## Evidencia

72 mensajes de ataque en 9 técnicas (`tests/data/adversarial.json`), 5 preguntas mixtas y 7 pedidos de promesas, más un banco de 75 preguntas ajenas y 20 cercanas al negocio (`tests/data/fuera_de_alcance_evaluacion.json`). Ninguno se obedece ni se responde con un documento; de las 75 ajenas se rechazan 73, y las otras 2 son decisiones de diseño (un tema legal se deriva y un paquete a la luna recibe la política de envíos).

Salvedad: el banco lo escribí yo y varias correcciones salieron de sus fallos, así que las cifras son optimistas. Una cláusula ajena sin verbo de tarea ("si hace calor") sigue llegando al modelo, quedan sin cubrir los ataques multi-turno largos, y la detección de inyección sigue acotada a lo inequívoco: no es una garantía.
