# ADR 0006: Reembolsos de hasta $500 y monto declarado por el cliente

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El documento 4 dice que los reembolsos mayores a $500 requieren la aprobación de un supervisor humano y que el agente no debe aprobarlos automáticamente. No dice quién aprueba los de $500 o menos ni que el agente deba aprobarlos. El enunciado agrega que el guardrail debe derivar los casos que los documentos indican que no debe manejar (entre ellos los reembolsos mayores a $500), lo que implica que los de hasta $500 sí los maneja, es decir, los responde sin derivar. Además, la tabla de pedidos no trae precios: el agente no puede conocer el valor real de una compra.

## Decisión

- Hasta $500 el agente no deriva: informa la política (se procesa en 5 a 10 días hábiles después de recibir el producto devuelto, al mismo método de pago original), aclara que con ese monto no hace falta la aprobación de un supervisor y avisa que, si el valor real de la compra lo supera, sí la requiere y hay que escribir a soporte@tiendahogar.example.
- El agente no dice que el reembolso esté aprobado ni que no pueda aprobarlo. Tres hechos del enunciado le impiden aprobar o ejecutar: la única tool es de solo lectura, el monto lo declara el cliente y no se puede verificar, y la política pone condiciones que el agente no puede comprobar (30 días, producto sin usar y en su empaque, o defecto cubierto por la garantía). Afirmar "tu reembolso está aprobado" sería inventar una acción y permitiría obtener una "aprobación" declarando un monto menor.
- No se inventa un catálogo de precios, porque sería agregar datos que el enunciado no da.
- Reembolso sin monto: en vez de volcar la política, el agente pregunta de cuánto fue la compra y en la misma pregunta da las dos ramas (hasta $500: 5 a 10 días hábiles, mismo método de pago; por encima de $500: lo aprueba un supervisor y se deriva). Con el monto en un mensaje posterior se aplica la regla (ADR 0008). Solo se pregunta si el cliente pide plata y no está preguntando por la política ("cuánto tardan los reembolsos?" no repregunta).

## Alternativas descartadas

- Una frase como "yo no apruebo reembolsos": contradice el documento, que solo lo prohíbe por encima de $500. Se eliminó del prompt.
- Derivar todo reembolso: contradice el enunciado y deja sin respuesta los de monto bajo.
- Confirmar el reembolso hasta $500: el agente no tiene cómo ejecutarlo ni verificarlo.

## Consecuencias

El agente es coherente con los documentos y no promete nada que no pueda cumplir. Depende del monto que declara el cliente: en producción vendría de la API de pedidos, y una API de aprobación aprobaría automáticamente hasta $500 y derivaría el resto a un supervisor por un evento (ver la sección de producción de `SUBMISSION.md`).
