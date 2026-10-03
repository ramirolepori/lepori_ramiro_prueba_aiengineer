# ADR 0005: Consulta de pedidos en tres capas

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

La tool `consultar_estado_pedido(order_id: str) -> dict` consulta una tabla mock (ORD-1001 a ORD-1004) y debe devolver "No encontrado", sin inventar, para un número que no existe. Los clientes escriben "pedido 1001", "ord 1001", "compra nro 1003" o "n°2000", o preguntan por su pedido sin dar el número.

## Decisión

1. Extracción flexible del número (`pedidos.py`): el prefijo `ORD` con cualquier separador y las formas "pedido", "orden", "compra", "nro", "n°" y "#", también en listas. Se normaliza a `ORD-XXXX` y la respuesta muestra qué número se entendió. Un número suelto sin contexto de pedido, o seguido de una unidad ("500 pesos", "1001 años"), no cuenta.
2. Identificadores con otro formato (`DRO-1002`, `ORD-ABCD`, `OD-1002`): no se corrigen en silencio. El agente dice que no encontró ese identificador y cuál es el formato.
3. Intención por significado: "ya salió lo que compré?" sin número se reconoce si habla de algo propio, y el agente pide el número. "Cuánto tarda el envío?" a secas es una pregunta de política, y una compra futura no es un pedido.
4. No se busca por nombre de producto: un cliente real puede tener varios pedidos y adivinar sería inventar datos.

## Alternativas descartadas

- Tolerar la letra O por el cero ("ORD-1O01"): puede atribuir mal un pedido.
- Un modelo de lenguaje para extraer el número: rompe el flujo decidido por código (ADR 0002).

## Evidencia

Extracción de números: 41 de 41 en desarrollo y 17 de 17 en prueba. Intención sin número, con embeddings: 10 de 10 y 4 de 4. En los lotes de frases ajenas, la extracción pasó de 5 de 9 a 9 de 9 y los identificadores raros de 0 de 5 a 5 de 5 (ADR 0010).
