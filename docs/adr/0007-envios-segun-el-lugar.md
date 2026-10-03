# ADR 0007: Plazo de envío según el lugar, con la capital igual a CABA

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El documento 3 dice "Envíos a la capital: 2-3 días hábiles. Envíos a otras ciudades: 5-7 días hábiles", sin decir qué ciudad es "la capital". Con "Soy de Córdoba capital" un modelo de 7 mil millones de parámetros inventó el mapeo y lo cambió de una corrida a otra. Es un dato que decide la respuesta y el documento no lo da.

## Decisión

"La capital" es la Ciudad de Buenos Aires (CABA), y la respuesta lo declara. El plazo lo decide el código (`lugares.py`, `data/lugares.json`) sobre el lugar identificado con un diccionario, no sobre el texto libre.

- CABA, Capital Federal, "la capital del país" y sus barrios: 2-3 días hábiles.
- Capitales provinciales ("Córdoba capital"): cuentan como otras ciudades (5-7 días) y la respuesta lo aclara.
- "Buenos Aires" a secas es ambiguo: se repregunta con los dos plazos incluidos.
- Un país o ciudad del exterior: los envíos internacionales no están disponibles.
- Un lugar que no está en el diccionario ("Zapala") no se adivina: se repregunta si es una ciudad de Argentina fuera de CABA.
- Tolera faltas ("cordova"). Sin lugar se informan los dos plazos y se pregunta la ciudad.
- Si la pregunta mezcla el envío con otro tema, el plazo se agrega ya resuelto y el modelo solo redacta lo otro.

## Alternativas descartadas

- Dejar que el modelo decida cuál es la capital: inventa y cambia entre corridas.
- Tomar toda capital provincial como "la capital": el documento habla de una sola.
- Un servicio de geocodificación: dependencia externa innecesaria.

## Consecuencias

La respuesta de envíos es exacta y se prueba sin modelo (`tests/test_lugares.py`). El diccionario es una muestra, no un catálogo. En producción el lugar saldría de la dirección de entrega.
