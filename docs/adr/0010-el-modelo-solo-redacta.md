# ADR 0010: El modelo solo redacta, y lo obligatorio lo agrega el código

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

Un modelo chico puede ignorar lo que no se le pide con fuerza, deformar cifras, inventar citas o cubrir una sola de dos políticas. Las pruebas con `qwen2.5:7b` mostraron estos problemas: omitía a veces la aclaración de la regla de los $500 y el aviso de pedir el número de pedido; el modelo de 3B inventaba citas y cifras; una pregunta que mezcla garantía y devolución recibía a veces una respuesta que cubría solo una; y las respuestas largas sumaban texto de más.

## Decisión

El modelo recibe solo el contexto recuperado (documentos y pedidos), un prompt que le pide ser breve ("una o dos oraciones, sin repetir la pregunta ni agregar consejos") y que no confirme ni prometa que un reembolso o una devolución fue aprobado o ejecutado. Todo lo demás lo hace el código después de generar:

- Validación de la salida (`_problema_de_salida`): se descarta la respuesta, y se usa el modo offline, si trae cifras o correos que no estaban en el contexto, o si es demasiado corta (por ejemplo un sí o no sin explicación), o si trae varias palabras largas que no están en el contexto (cuatro o más: suele ser un consejo o un paso inventado, como "contactá al service para la reparación o el reemplazo"). Se calibró con respuestas reales de `qwen2.5:7b`: las inventadas tenían 4 o más y las correctas 2 o menos. Las citas se limpian: solo quedan las de documentos recuperados, una cita en el medio de la frase ("Según la [garantia], ...") pasa al final, una referencia que quedó sin cita ("Según la, ...") se borra, y si falta se agrega la principal.
- Notas obligatorias agregadas por código, con o sin modelo: la aclaración de la regla de los $500, el pedido del número de pedido y la pregunta del monto. El modelo no las recibe.
- Cobertura: si la pregunta toca dos políticas (por ejemplo garantía y devolución) y el modelo solo cubrió una, el código revisa los dos documentos mejor rankeados y agrega, con su título y su cita, el texto de los que la respuesta no cubre. Un documento cuenta como cubierto si la respuesta lo cita o si ya usa alguna de sus cifras (por ejemplo "12 meses"). Solo se completan los dos mejores y solo los que la pregunta nombra ("garantía", "devolver", "reembolso"), porque si no se sumaban reembolsos a una pregunta de devolución.
- El plazo de devolución, cuando el cliente dice cuánto hace que compró lo que quiere devolver ("hace 45 días", "hace 3 semanas", "compré ayer"), se calcula por código (`plazos.py`) y se responde con el Doc 2 aplicado a esos días ("pasaron más de 30 días: solo se acepta con un defecto cubierto por la garantía", y la garantía si corresponde). El modelo razonaba mal esta cuenta: decía "no se aceptan devoluciones después de 30 días si el producto no fue usado" o aceptaba una devolución a los 40 días. No se aplica si los días son de otra cosa (la espera de un reembolso) ni a un producto de liquidación, personalizado o hecho a pedido, que no se devuelve en ningún caso.
- Las preguntas por el canal humano ("con quién me puedo contactar?") se responden con una frase fija con el correo del Doc 5 y no con el modelo, que completaba con motivos que el documento no dice ("quejas sobre reembolsos"). Si además preguntan por un tema de los documentos (un reembolso demorado), se responde ese tema y después el canal.
- El plazo de envío, cuando se conoce el lugar, se redacta por plantilla y se le saca al modelo del contexto (ADR 0007). Una consulta solo de pedidos usa una plantilla exacta y no llama al modelo.
- Una consulta de más de 2000 caracteres se recorta, y el modelo no se llama si saltó un guardrail.

## Alternativas descartadas

- Confiar en que el modelo copie las aclaraciones obligatorias: la calidad era de 8 de 10 y subió a 10 de 10 al moverlas al código.
- Responder con la oración exacta del documento, sin modelo, cuando la pregunta corresponde a una sola oración: casi instantáneo y no puede inventar, pero le quita naturalidad. Descartada por Ramiro.
- Limitar la respuesta con un tope de tokens: no mejoró la calidad ni acortó las respuestas y puede cortarlas, así que no se usa.

## Consecuencias

La respuesta es verificable aunque el modelo sea chico y el modo offline siempre es una salida válida. Costo de completar la cobertura, medido en el peor caso (el modelo cita solo el primer documento) sobre las 102 preguntas del conjunto de RAG con documentos esperados: se agrega texto en 9, en 7 era útil y en 2 era de más. La indicación de brevedad del prompt ("una o dos oraciones, sin repetir la pregunta ni agregar consejos") redujo el largo medio de las respuestas de 20 a 16 palabras en 10 preguntas con datos esperados fijos, sin perder calidad.
