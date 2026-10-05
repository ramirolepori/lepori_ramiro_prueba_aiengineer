# ADR 0004: Decisiones donde los documentos callan

Estado: aceptada. Octubre de 2026.

## Reembolsos de hasta $500

El Doc 4 exige un supervisor para los reembolsos mayores a $500 y no dice qué pasa con los de $500 o menos. La tabla de pedidos no trae precios, así que el monto es el que declara el cliente.

- Hasta $500 el agente no deriva: informa la política (5 a 10 días hábiles, al mismo método de pago) y aclara que con ese monto no hace falta un supervisor, y que si el valor real lo supera sí. Si la consulta ya se deriva por otro monto, esa aclaración no se agrega.
- No dice que el reembolso esté aprobado: no puede ejecutarlo ni verificar el monto o las condiciones. Prometerlo permitiría "aprobar" un reembolso declarando un monto menor.
- Sin monto, pregunta de cuánto fue la compra y da las dos ramas en la misma pregunta.
- El tope se aplica por reembolso y no a la suma de varios.
- Descartado: "yo no apruebo reembolsos" (contradice el documento) y derivar todo reembolso (contradice el enunciado).

## Plazo de envío según el lugar

El Doc 3 dice "Envíos a la capital: 2-3 días hábiles. Envíos a otras ciudades: 5-7 días hábiles" sin decir cuál es la capital. Un modelo de 7 mil millones de parámetros inventó el mapeo y lo cambió entre corridas, así que lo decide el código (`lugares.py`, `data/lugares.json`) y la respuesta lo declara.

- "La capital" es la Ciudad de Buenos Aires (CABA), sus barrios y "capital federal": 2-3 días. Una capital provincial ("Córdoba capital") cuenta como otra ciudad: 5-7 días.
- "Buenos Aires" a secas es ambiguo: se repregunta con los dos plazos incluidos. Un lugar del exterior: no hay envíos internacionales. Un lugar que no está en el diccionario ("Zapala") no se adivina: se confirma si es una ciudad argentina fuera de CABA.
- Tolera faltas ("cordova"), responde varios lugares a la vez y, sin lugar, informa los dos plazos y pregunta la ciudad.
- Descartado: dejar que el modelo elija la capital, tomar toda capital provincial como "la capital" y una API de geocodificación.

El diccionario es una muestra, no un catálogo. En producción el lugar saldría de la dirección de entrega y el monto de la API de pedidos.
