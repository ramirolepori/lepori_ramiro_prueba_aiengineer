# ADR 0004: RAG híbrido (embeddings y BM25) y umbral por margen

Estado: aceptada. Fecha: octubre de 2026. Decidió: Ramiro.

## Contexto

La plantilla pregunta por el chunking, los embeddings y el umbral, y qué pasa si nada lo supera. Los 5 documentos miden menos de 400 caracteres y son una sola política cada uno. BM25 es explicable pero no ve paráfrasis ni faltas ("garatnia").

## Decisión

- Chunking: no. Cada documento es un fragmento, porque partirlo separaría frases que se necesitan juntas (la regla de devoluciones y su excepción). `rag.dividir` queda para un corpus mayor (fragmentos de unos 600 caracteres alineados a títulos).
- Recuperador híbrido (`rag.py`): `embeddinggemma` más BM25, fusionados por posición. Cada documento se compara entero y por oración, y vale la mayor similitud. Una consulta con varias cláusulas se recupera por cláusula, porque un tema fuerte tapaba al otro.
- Umbral por margen, no absoluto, para que funcione con otro modelo de embeddings: un documento es relevante si supera por 0,08 a la mayor similitud con las preguntas de `data/fuera_de_alcance.json`, o si BM25 lo considera relevante. Se descartan los que quedan más de 0,06 por debajo del mejor, hasta 3.
- Si ninguno supera el umbral y no hay pedido, el agente dice que no tiene esa información y no llama al modelo.
- BM25 es el respaldo si fallan los embeddings. Usa una tabla corta de conceptos, corrección de faltas leves en palabras del dominio (misma primera letra) y no acepta una palabra suelta ("capital" en "capital de Francia"). Un documento que BM25 reconoce por una palabra explícita no se descarta por una diferencia chica de similitud.

## Alternativas descartadas

- Solo BM25: no recupera paráfrasis (queda como respaldo).
- Solo embeddings con el documento entero: 77 % de recall en desarrollo.
- Solo por oración sin BM25: se equivoca con "capital de Francia".
- Prefijos de tarea de `embeddinggemma`: no mejoraron (87 % contra 91 %).

## Evidencia

122 preguntas (`tests/data/rag_evaluacion.json`) divididas en desarrollo (84) y prueba (38):

| Recuperación | Desarrollo: recall, ajenas rechazadas | Prueba: recall, ajenas rechazadas |
| --- | --- | --- |
| BM25 solo | 68/70, 13 de 14 | 29/32, 6 de 6 |
| Híbrido con `embeddinggemma` | 67/70, 13 de 14 | 30/32, 6 de 6 |

Con un banco aparte de 75 preguntas ajenas al negocio, el ajuste de BM25 llevó el rechazo sin embeddings de 66 a 73 (ADR 0011). Fallos que quedan: paráfrasis lejanas ("mandan a otros países?") y preguntas que mezclan dos documentos, donde a veces solo se recupera uno. Salvedad: el conjunto lo escribió el autor del código.
