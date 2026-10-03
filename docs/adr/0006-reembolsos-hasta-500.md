# ADR 0006: Reembolsos de hasta $500 y monto declarado por el cliente

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El documento 4 dice que los reembolsos mayores a $500 requieren aprobación de un supervisor y que el agente no debe aprobarlos automáticamente. No dice qué pasa con los de $500 o menos, y el enunciado implica que esos sí los maneja el agente. La tabla de pedidos no trae precios: el agente no conoce el valor real de una compra.

## Decisión

- Hasta $500 el agente no deriva: informa la política (5 a 10 días hábiles después de recibir el producto, al mismo método de pago), aclara que con ese monto no hace falta un supervisor y avisa que si el valor real lo supera sí la requiere y hay que escribir a soporte@tiendahogar.example. Si la consulta ya se deriva por otro monto, esa aclaración no se agrega.
- El agente no dice que el reembolso esté aprobado. No puede ejecutarlo (la tool es de solo lectura), no puede verificar el monto (lo declara el cliente) ni las condiciones de la política (30 días, producto sin usar). Prometerlo sería inventar una acción y permitiría "aprobar" un reembolso declarando un monto menor.
- No se inventa un catálogo de precios.
- Reembolso sin monto: en vez de volcar la política, el agente pregunta de cuánto fue la compra y en la misma pregunta da las dos ramas (hasta $500 y por encima). Solo pregunta si el cliente pide plata y no está preguntando por la política (ADR 0008).

## Alternativas descartadas

- "Yo no apruebo reembolsos": contradice el documento, que lo prohíbe solo por encima de $500.
- Derivar todo reembolso: contradice el enunciado.
- Confirmar el reembolso hasta $500: el agente no puede ejecutarlo ni verificarlo.

## Consecuencias

El agente es coherente con los documentos y no promete lo que no puede cumplir. En producción el monto vendría de la API de pedidos y una API de aprobación aprobaría hasta $500 y derivaría el resto a un supervisor.
