# Arquitectura del agente de soporte de TiendaHogar

Cómo está armado el agente y cómo extenderlo. El porqué de cada decisión está en los [ADR](adr/README.md).

## Flujo de una pregunta

```
cliente ── pregunta ──► AgenteSoporte.responder(pregunta, sesion=None)
   1. entrada vacía o de más de 2000 caracteres ─► se pide la consulta o se recorta
   2. inyección de prompt ─► rechazo, sin modelo
   3. sesión: si hay un dato pendiente y el mensaje lo responde ─► consulta completa
   4. guardrail (reglas + embeddings, o n-gramas) ─► derivación a soporte@tiendahogar.example, sin modelo
        pregunta mixta: antes se responde la parte permitida
   5. pedidos: ORD-XXXX, "pedido 1001", "n°2000" ─► consultar_estado_pedido (tabla mock)
   6. RAG (embeddings + BM25, por consulta y por cláusula)
        nada relevante ─► "no tengo esa información" (o pide el número de pedido)
   7. envíos: el lugar decide el plazo, por plantilla
   8. redacción: con modelo (solo el contexto recuperado) o, sin modelo, citando los documentos
   9. validación de la salida, cobertura y notas obligatorias, agregadas por código ─► Respuesta
        (cada paso queda en una traza JSONL con sus tiempos)
```

Lo que el enunciado trata como regla (derivar, no inventar, no aprobar reembolsos) se resuelve en código antes o después del modelo, nunca dentro de él (ADR 0002).

## Módulos

Todo está en `src/tiendahogar/` y usa solo la librería estándar.

| Módulo | Responsabilidad |
| --- | --- |
| `agent.py` | El flujo de arriba: `AgenteSoporte`, `Respuesta`, preguntas mixtas, validación de la salida y notas |
| `guardrails.py`, `semantica.py` | Reglas de derivación e inyección; clasificación por significado (embeddings y n-gramas) |
| `montos.py` | Montos en distintos formatos (`$1.000`, `2k`, `2 lucas`, `mil quinientos`) |
| `rag.py`, `embeddings.py` | BM25, recuperador híbrido con umbral por margen, cliente de embeddings con caché |
| `pedidos.py` | `consultar_estado_pedido`, tabla mock y extracción flexible del número |
| `lugares.py`, `plazos.py` | Plazo de envío según el lugar (`data/lugares.json`) y plazo de devolución según los días |
| `sesion.py`, `recuerdos.py` | Memoria de la conversación: dato pendiente, repreguntas y lo que el cliente ya dijo |
| `llm.py`, `config.py` | Clientes OpenAI-compatible y Anthropic con `urllib`, y variables de entorno |
| `evaluacion.py`, `independiente.py`, `rendimiento.py`, `tiempos.py` | Mediciones de calidad y de latencia |

Datos en `src/tiendahogar/data/`: `docs/` (los 5 documentos del enunciado, sin editar), `anclas.json` (frases de ejemplo del guardrail), `fuera_de_alcance.json` (referencia del umbral del RAG) y `lugares.json`. Datos de evaluación en `tests/data/`.

## Contratos

- `consultar_estado_pedido(order_id: str) -> dict`: con `order_id`, `encontrado`, `producto`, `estado` y `entrega_estimada`, o `encontrado: False` y `estado: "No encontrado"`. Nunca inventa datos.
- `AgenteSoporte.responder(pregunta, sesion=None) -> Respuesta`. Sin `sesion`, cada pregunta es independiente.
- `Respuesta`: `texto`, `estado` (`respondido`, `escalado`, `sin_informacion` o `bloqueado`), `fuentes`, `escalamientos`, `pedidos`, `traza` y `tiempos`. La traza no guarda el texto del cliente.

## Cómo extender el agente

- Un documento nuevo: agregar el `.md` a `data/docs/` (se indexa solo) y medir con `python -m tiendahogar.evaluacion rag`.
- Una categoría de derivación: reglas en `guardrails.py`, frases de ejemplo en `data/anclas.json` y casos en `tests/data/guardrail_evaluacion.json`.
- Un lugar de envío: agregarlo a `data/lugares.json`.
- Un dato que el agente repregunte: definirlo en `sesion.py` y `agent.py`, con tests en `tests/test_sesion.py`.
- Un proveedor de modelos: si es compatible con OpenAI alcanza con `LLM_BASE_URL`; si no, un cliente nuevo en `llm.py` con `generar(sistema, prompt)`.

Después de un cambio, correr `python -m pytest tests/`. Un lote de frases ajenas se mide una sola vez antes de corregir (ADR 0010).
