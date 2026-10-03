# ADR 0007: Plazo de envío según el lugar, con la capital igual a CABA

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

El documento 3 dice "Envíos a la capital: 2-3 días hábiles. Envíos a otras ciudades: 5-7 días hábiles. Envíos internacionales no están disponibles actualmente", sin decir qué ciudad es "la capital". Con "Soy de Córdoba capital, cuánto tarda el envío?" un modelo de 7 mil millones de parámetros contestó que Córdoba capital tarda 2-3 días, que Salta capital tarda 5-7 ("no es la capital") y que Buenos Aires tarda 2-3: inventa el mapeo y lo cambia de una corrida a otra. Es un dato que decide la respuesta y que el documento no da.

## Decisión

"La capital" es la Ciudad de Buenos Aires (CABA), la capital del país. Es una interpretación y la respuesta la declara ("Entiendo 'la capital' como la Ciudad de Buenos Aires (CABA)"). El plazo lo decide el código (`lugares.py` y `data/lugares.json`), no el modelo. Es la técnica habitual para un dato de tipo lugar en un chatbot (slot): identificar el lugar con un diccionario de entidades y decidir sobre el dato resuelto, no sobre el texto libre.

- CABA, Capital Federal, "la capital del país", "Buenos Aires capital" y los barrios de la Ciudad: capital, 2-3 días hábiles.
- Capitales provinciales ("Córdoba capital", "Mendoza capital", "la capital de Salta"): no son "la capital" del documento, cuentan como otras ciudades (5-7 días hábiles) y la respuesta lo aclara.
- "Buenos Aires" a secas es ambiguo (la Ciudad o la provincia): se repregunta con los dos plazos incluidos. El Gran Buenos Aires y la provincia son otras ciudades.
- Un país o una ciudad del exterior: los envíos internacionales no están disponibles. Si se nombra un país, manda sobre una ciudad homónima ("Córdoba, España").
- Un lugar que no está en el diccionario pero viene tras una pista fuerte ("soy de Zapala") se reconoce como desconocido, no se adivina y se repregunta si es una ciudad de Argentina fuera de la Ciudad de Buenos Aires.
- Tolera faltas de ortografía ("cordova"). Los nombres que son palabras comunes (Pilar, Flores, Once) solo cuentan tras una preposición.
- Sin lugar ("cuánto tarda el envío a mi casa?") se informan los dos plazos y se pregunta la ciudad.
- Si la pregunta mezcla el envío con otro tema, el modelo solo redacta la otra parte: el plazo de envío se le saca del contexto y se agrega ya resuelto, con la cita `[envios]`.

## Alternativas descartadas

- Dejar que el modelo decida cuál es la capital: inventa y cambia entre corridas.
- Tomar toda capital provincial como "la capital": el documento habla de una sola.
- Un servicio de geocodificación: es una dependencia externa que un ejercicio acotado no necesita.

## Consecuencias

La respuesta de envíos es exacta, con las cifras del documento, y se prueba sin modelo. El diccionario es una muestra, no un catálogo de localidades: un lugar que no figura cae en "desconocido". En producción el lugar saldría de la dirección de entrega del cliente, no del texto de la consulta. Los casos están en `tests/test_lugares.py`.
