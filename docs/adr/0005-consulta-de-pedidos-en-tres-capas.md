# ADR 0005: Consulta de pedidos en tres capas

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

La tool `consultar_estado_pedido(order_id: str) -> dict` consulta una tabla mock con ORD-1001 a ORD-1004 y debe devolver un "no encontrado" claro, sin inventar, para un número que no existe. Llamar a la tool solo cuando aparece el texto exacto `ORD-XXXX` es frágil: los clientes escriben "pedido 1001", "ord 1001", "mi pedido es el 1001", "compra nro 1003" o "n°2000", o preguntan por su pedido sin dar el número.

## Decisión

1. Extracción flexible del número (`pedidos.py`). Se acepta el prefijo `ORD` con cualquier separador o guion, y las formas "pedido", "orden", "compra", "encargo", "transacción", "nro", "n°" y "#", también en listas ("pedidos 1001 y 1004"). Se normaliza a `ORD-XXXX` y la respuesta muestra qué número se entendió, para que el cliente corrija si hubo un malentendido. Un número suelto sin contexto de pedido no cuenta (puede ser un monto o un plazo), ni uno seguido de una unidad ("1001 años", "500 pesos").
2. Identificadores con otro formato (`DRO-1002`, `ORD1OO1`, `ORD-ABCD`, `OD-1002`). No se corrigen en silencio: el agente responde que no encontró ese identificador, lo nombra y dice cuál es el formato (ORD-XXXX, por ejemplo ORD-1001).
3. Intención por significado. Una categoría "consulta de pedido" en el clasificador semántico reconoce "ya salió lo que compré?" aunque no diga "pedido" ni dé un número, siempre que hable de algo propio ("mi", "compré", "hice un pedido"), y en ese caso el agente pide el número. "Cuánto tarda el envío?" a secas es una pregunta de política, no una consulta de estado. Una compra futura ("voy a comprar...") tampoco lo es.
4. No se busca por nombre de producto. La tabla tiene un pedido por producto, pero un cliente real puede tener varios, y adivinar sería inventar datos, que el enunciado prohíbe.

## Alternativas descartadas

- Tolerar la letra O por el cero ("ORD-1O01"): puede atribuir mal un pedido.
- Usar un modelo de lenguaje para extraer el número: rompe la decisión de que el flujo lo decide el código (ADR 0002).
- Buscar por producto: ver el punto 4.

## Consecuencias

La tool se llama de forma predecible y siempre responde con datos de la tabla o con "no encontrado". Con una sesión, el número pedido se puede dar en un mensaje posterior (ADR 0008).

## Evidencia

Extracción de números: 41 de 41 en desarrollo y 17 de 17 en prueba. Intención de consulta sin número, con embeddings: 10 de 10 y 4 de 4, con 1 falso positivo en 10 en desarrollo (n-gramas: 9 de 10 y 2 de 4). En los lotes de frases ajenas, la extracción pasó de 5 de 9 a 9 de 9, y los identificadores con formato raro de 0 de 5 a 5 de 5 (ADR 0011).
