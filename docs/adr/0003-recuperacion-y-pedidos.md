# ADR 0003: Recuperación de documentos y consulta de pedidos

Estado: aceptada. Octubre de 2026.

## Contexto

Los 5 documentos miden menos de 400 caracteres y son una política cada uno. BM25 es explicable pero no ve paráfrasis ni faltas. La tool `consultar_estado_pedido(order_id: str) -> dict` consulta una tabla mock y debe decir "No encontrado", sin inventar, si el número no existe. Los clientes lo escriben de muchas formas o no lo dan.

## Decisión

Recuperación (`rag.py`):
- Sin chunking: cada documento es un fragmento, porque partirlo separaría frases que se necesitan juntas (la regla de devoluciones y su excepción). `rag.dividir` queda para un corpus mayor.
- Híbrido: `embeddinggemma` más BM25, fusionados por posición. Cada documento se compara entero y por oración, y una consulta con varias cláusulas se recupera por cláusula.
- Umbral por margen, no absoluto, para que valga con otro modelo de embeddings: un documento es relevante si supera por 0,08 a la mayor similitud con las preguntas de `data/fuera_de_alcance.json`, o si BM25 lo considera relevante. Si ninguno lo supera y no hay pedido, el agente dice que no tiene esa información y no llama al modelo.
- BM25 es el respaldo si fallan los embeddings. No acepta una palabra suelta ("capital" en "capital de Francia") ni toma "La Plata" o "Mar del Plata" por dinero.

Pedidos (`pedidos.py`):
- El número se extrae de `ORD-1001`, "pedido 1001", "compra nro 1003", "n°2000", en palabras ("mil uno") y en listas, y la respuesta muestra qué número entendió. Un número suelto o seguido de una unidad ("500 pesos") no cuenta.
- Un identificador con otro formato (`DRO-1002`, `ORD-1001abc`) no se corrige en silencio: se dice que no se encontró y cuál es el formato. No se busca por nombre de producto, porque adivinar sería inventar.
- Sin número ("ya salió lo que compré?") el agente lo pide. "Cuánto tarda el envío a mi casa?" es una pregunta de política, no un pedido.
- Lo que el cliente escribe como identificador no se guarda en la traza (podría ser un DNI o una tarjeta).

## Descartado

Solo BM25 (no recupera paráfrasis), solo embeddings con el documento entero (77 % de recall), tolerar la letra O por el cero (puede atribuir mal un pedido) y un modelo de lenguaje para extraer el número.

## Evidencia

122 preguntas (84 de desarrollo y 38 de prueba). Recall del híbrido: 67 de 70 y 30 de 32 (BM25 solo: 68 de 70 y 29 de 32); preguntas ajenas rechazadas: 13 de 14 y 6 de 6. Extracción de números de pedido: 41 de 41 y 17 de 17. Fallos que quedan: paráfrasis lejanas ("mandan a otros países?") y preguntas que mezclan dos documentos, donde a veces se recupera solo uno.
